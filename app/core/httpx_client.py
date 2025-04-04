import json
from typing import Optional, Dict, Any

from fastapi import Request
from httpx import AsyncClient, Response
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core import logger, get_settings
from app.core.decorators import log_and_catch

settings = get_settings()


class HTTPXClient:
    """
    Асинхронный HTTP-клиент-сервис с повторными попытками (retry) и логированием.
    Использует базовый httpx.AsyncClient, который управляется через lifespan.
    Предназначен для внедрения через FastAPI DI.
    """

    def __init__(self, client: AsyncClient):
        """
        Инициализируется базовым httpx.AsyncClient.
        Args:
            client (AsyncClient): Экземпляр httpx.AsyncClient.
        """
        self.client = client  # Сохраняем базовый клиент

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda r: logger.warning(
            f"[HTTPX] Повтор {r.attempt_number}: {type(r.outcome.exception()).__name__} — {r.outcome.exception()}"
        )
    )
    @log_and_catch(debug=settings.DEBUG_HTTP)
    async def fetch(
            self,  # Добавляем self
            url: str,
            method: str = "GET",
            headers: Optional[Dict[str, str]] = None,
            cookies: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None,
            data: Optional[Dict[str, Any]] | str = None,
            timeout: Optional[float] = None,
            **kwargs  # Добавляем kwargs для возможной передачи доп. параметров в request
    ) -> Dict[str, Any]:
        """Асинхронный HTTP-запрос с повторными попытками и обработкой ответа."""
        request_timeout = timeout if timeout is not None else 30.0  # Используем стандартный таймаут httpx, если не передан

        # Используем self.client для выполнения запроса
        response: Response = await self.client.request(
            method=method,
            url=url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            timeout=request_timeout,
            **kwargs
        )

        response.raise_for_status()  # Ошибка, если 4xx/5xx

        json_data = None
        content_type = response.headers.get("Content-Type", "").lower()  # Приводим к нижнему регистру для надежности

        if "application/json" in content_type:
            try:
                # response.json() используем ТОЛЬКО для application/json
                if response.content:  # Проверяем, что есть что парсить
                    json_data = response.json()
                    logger.debug(f"Успешно распарсен JSON ответ для {url}")
                else:
                    logger.debug(f"Content-Type application/json, но тело ответа пустое для {url}")
            except json.JSONDecodeError as e:  # Ловим ошибку парсинга JSON
                logger.warning(
                    f"Не удалось декодировать JSON из ответа {url} (Content-Type: {content_type}): {e}. Текст: {response.text[:200]}...")
                json_data = None  # Оставляем None

        elif "text/html" in content_type:
            # Для text/html пробуем json.loads из УЖЕ ДЕКОДИРОВАННОГО текста
            if response.text:  # Проверяем, что текст не пустой
                try:
                    json_data = json.loads(response.text)
                    logger.debug(f"Успешно распарсен JSON из text/html ответа для {url}")
                except json.JSONDecodeError:
                    # Ошибки нет, просто это не JSON, замаскированный под HTML
                    logger.debug(f"Content-Type text/html для {url}, но тело не является JSON.")
                    json_data = None
            else:
                logger.debug(f"Content-Type text/html для {url}, но тело ответа пустое.")
                json_data = None
        else:
            # Для всех остальных типов (XML, text/plain и др.) не пытаемся парсить JSON
            logger.debug(f"Content-Type '{content_type}' для {url}. JSON парсинг не выполняется.")
            json_data = None

        return dict(
            status_code=response.status_code,
            headers=dict(response.headers),
            cookies=dict(response.cookies),
            content=response.content,
            text=response.text,
            json=json_data
        )


async def get_http_service(request: Request) -> HTTPXClient:
    """
    Зависимость FastAPI для получения экземпляра сервиса HTTPXClient.
    Использует базовый клиент, хранящийся в app.state.
    """
    # Достаем базовый клиент из app.state, который был создан в lifespan
    base_client: Optional[AsyncClient] = getattr(request.app.state, "http_client", None)
    if base_client is None:
        # Это не должно произойти, если lifespan настроен правильно
        logger.critical("Базовый HTTPX клиент не найден в app.state!")
        raise RuntimeError("Базовый HTTPX клиент не был инициализирован.")
    # Создаем и возвращаем экземпляр нашего сервиса HTTPXClient
    return HTTPXClient(client=base_client)
