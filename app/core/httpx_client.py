import json
from typing import Optional, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import logger
from app.core.decorators import log_and_catch
from app.core.config import get_settings

settings = get_settings()
DEBUG_HTTP = settings.DEBUG_HTTP

class HTTPXClient:
    """
    Асинхронный HTTP-клиент с повторными попытками (retry).

    **Использование:**

    **GET-запрос**
    ```python
    response = await HTTPClient.fetch("https://example.com")
    print(response["text"])  # Текст ответа
    ```

    **POST-запрос**
    ```python
    response = await HTTPClient.fetch("https://example.com/api", method="POST", data={"key": "value"})
    print(response["json"])  # JSON-ответ
    ```

    **Возвращаемый словарь содержит:**
      - `status_code` → Код ответа (int)
      - `headers` → Заголовки (dict)
      - `cookies` → Cookies (dict)
      - `text` → Текст ответа (str)
      - `json` → JSON-ответ (dict | None, если ответ не JSON)
    """

    _instance: Optional[httpx.AsyncClient] = None  # Глобальный клиент

    @classmethod
    async def initialize(cls):
        """Инициализация HTTP-клиента."""
        if cls._instance is None:
            cls._instance = httpx.AsyncClient(timeout=30.0, verify=False)

    @classmethod
    async def shutdown(cls):
        """Закрытие HTTP-клиента."""
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Возвращает клиент, если он инициализирован, иначе ошибка."""
        if cls._instance is None:
            raise RuntimeError("HTTP-клиент не инициализирован. Вызовите initialize() перед использованием.")
        return cls._instance

    @classmethod
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=lambda r: logger.warning(
            f"[HTTPX] Повтор {r.attempt_number}: {type(r.outcome.exception()).__name__} — {r.outcome.exception()}"
        )
        # before_sleep=lambda retry_state: logger.warning(
        #     f"[HTTPXClient] Повтор запроса {retry_state.attempt_number} "
        #     f"на {retry_state.args[1] if len(retry_state.args) > 1 else 'неизвестный URL'} "
        #     f"({retry_state.outcome.exception()})"
        # )
    )
    @log_and_catch(debug=settings.DEBUG_HTTP)
    async def fetch(
            cls,
            url: str,
            method: str = "GET",
            headers: Optional[Dict[str, str]] = None,
            cookies: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None,
            data: Optional[Dict[str, Any]] | str = None,
            timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Асинхронный HTTP-запрос с повторными попытками."""
        # try:
        client = cls.get_client()
        request_timeout = timeout if timeout is not None else 30.0
        response = await client.request(
            method=method,
            url=url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            timeout=request_timeout,
        )

        response.raise_for_status()  # Ошибка, если 4xx/5xx

        json_data = None
        if "text/html" in response.headers.get("Content-Type", ""):
            try:
                json_data = json.loads(response.text)
            except ValueError as e:
                json_data = None  # Если не удалось декодировать JSON

        elif "application/json" in response.headers.get("Content-Type", ""):
            try:
                json_data = response.json()
            except ValueError as e:
                json_data = None  # Если не удалось декодировать JSON

        return dict(
            status_code=response.status_code,
            headers=dict(response.headers),
            cookies=dict(response.cookies),
            content=response.content,
            text=response.text,
            json=json_data

        )

        # except httpx.HTTPStatusError as e:
        #     # Логируем ошибку, если статус ответа 4xx/5xx
        #     logger.error(f"Ошибка HTTP: {e.response.status_code} - {e.response.text}")
        #     raise
        #
        # except AttributeError as e:
        #     logger.error(f"AttributeError в fetch(): {e}")  # Выведет точную ошибку
        #     raise
