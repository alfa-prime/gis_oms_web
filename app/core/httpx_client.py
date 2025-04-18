import json
from typing import Optional, Dict, Any

# from fastapi import Request
from httpx import AsyncClient, Response, HTTPStatusError, RequestError,TimeoutException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.core import logger, get_settings
from app.core.decorators import log_and_catch

settings = get_settings()

# ---- Вспомогательная функция для retry ----
def _is_retryable_exception(exception) -> bool:
    """Определяет, стоит ли повторять запрос при этой ошибке."""
    # Повторяем при ошибках сети/сервера/таймаута/статуса 5xx
    # Не повторяем при 4xx, т.к. они обычно требуют исправления запроса
    if isinstance(exception, HTTPStatusError):
        return 500 <= exception.response.status_code < 600
    return isinstance(exception, (
        RequestError,
        TimeoutException
    ))


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

        # Метод для обработки ответа (парс JSON и т.д.)
    def _process_response(self, response: Response, url: str) -> dict: # noqa
        """Обрабатывает response и возвращает структурированный результат."""
        json_data = None
        content_type = response.headers.get("Content-Type", "").lower()

        if "application/json" in content_type:
            try:
                if response.content:
                    json_data = response.json()
                    logger.debug(f"Успешно распарсен JSON (application/json) ответ для {url}")
                else:
                    logger.debug(f"Content-Type application/json, но тело ответа пустое для {url}")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Не удалось декодировать JSON (application/json) из ответа {url}: {e}. Текст: {response.text[:200]}...")
        elif "text/html" in content_type:
            if response.text:
                try:
                    json_data = json.loads(response.text)
                    logger.debug(f"Успешно распарсен JSON (из text/html) ответа для {url}")
                except json.JSONDecodeError:
                    logger.debug(f"Content-Type text/html для {url}, но тело не является JSON.")
            else:
                logger.debug(f"Content-Type text/html для {url}, но тело ответа пустое.")
        else:
            logger.debug(f"Content-Type '{content_type}' для {url}. JSON парсинг не выполняется.")

        result = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "cookies": dict(response.cookies),
            "content": response.content,
            "text": response.text,
            "json": json_data
        }
        return result

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_exception),  # Используем фильтр
        retry_error_callback=lambda retry_state: logger.error(
            f"[HTTPX] Превышено количество попыток "
            f"({retry_state.attempt_number}) для {retry_state.args[1]  if len(retry_state.args) > 1 else 'URL?'} "
            f"после ошибки: {retry_state.outcome.exception()}"),
        before_sleep=lambda r: logger.warning(
            f"[HTTPX] Повтор {r.attempt_number} для {r.args[1] if len(r.args) > 1 else 'URL?'} "
            f"из-за: {type(r.outcome.exception()).__name__} - {r.outcome.exception()}"
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
            raise_for_status: bool = True,  # Флаг управления raise_for_status
            **kwargs  # Добавляем kwargs для возможной передачи доп. параметров в request
    ) -> Dict[str, Any]:
        """
        Основной метод для выполнения HTTP-запросов.
        Включает запрос, проверку статуса (опционально), обработку ответа,
        логирование и повторные попытки для определенных ошибок.
        """
        request_timeout = timeout if timeout is not None else 30.0  # Используем стандартный таймаут httpx, если не передан

        # --- Шаг 1: Выполнение запроса ---
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

        # --- Шаг 2: Проверка статуса (если нужно) ---
        # Ошибки будут пойманы и обработаны декоратором @retry (если retryable)
        if raise_for_status:
            try:
                response.raise_for_status()
            except HTTPStatusError as http_error:
                # Логируем 4xx/5xx ошибки, но пробрасываем дальше для retry
                logger.warning(f"[HTTPX] Статус ответа {http_error.response.status_code} для {url}.")
                raise http_error

        # --- Шаг 3: Обработка ответа ---
        # Ошибки здесь (кроме JSONDecodeError) будут пойманы @log_and_catch,
        # но НЕ вызовут retry (т.к. не подходят под _is_retryable_exception)
        processed_result = self._process_response(response, url)
        return processed_result



