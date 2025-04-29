import functools
import time
import traceback
from typing import Callable, Awaitable, Any, Type, Dict, TypeVar, ParamSpec

from fastapi import HTTPException, status, Request

from app.core import logger, get_settings

settings = get_settings()

P = ParamSpec("P")
R = TypeVar("R")


def log_and_catch(debug: bool = settings.DEBUG_HTTP) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Декоратор для логирования и перехвата ошибок в асинхронных HTTP-функциях (и не только).

    Логирует начало и конец выполнения функции, параметры и ошибки (если есть).
    Применяется в HTTPXClient и может применяться в других сервисах.

    Args:
        debug (bool): Включает подробное логирование параметров, результата и трейсов ошибок.

    Returns:
        Callable[..., Awaitable[Any]]: Обернутая функция.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Определяем контекст для лога (имя функции и базовые параметры)
            func_name = func.__name__
            # Пытаемся угадать 'метод' и 'url' из kwargs, если это HTTP-запрос
            method = kwargs.get("method", "FUNC")  # Используем FUNC как дефолт, если не HTTP
            url = kwargs.get("url", func_name)  # Используем имя функции, если URL не передан

            # Лог до вызова функции
            if debug:
                log_prefix = f"[{method}] {url}"  # Формируем префикс
                logger.debug(f"{log_prefix} — старт")
                # Логируем основные аргументы/параметры, если они есть
                args_preview = str(args)[:300] if args else ""
                kwargs_preview = str({k: v for k, v in kwargs.items() if k != 'http_service' and k != 'cookies'})[
                                 :500]  # Исключаем большие объекты
                if args_preview: logger.debug(f"{log_prefix} Args: {args_preview}...")
                if kwargs_preview and kwargs_preview != '{}': logger.debug(f"{log_prefix} Kwargs: {kwargs_preview}...")
                # Дополнительное логирование для HTTPX (если есть)
                if method != "FUNC":
                    if "params" in kwargs: logger.debug(f"{log_prefix} Params: {str(kwargs['params'])[:300]}...")
                    if "data" in kwargs: logger.debug(f"{log_prefix} Data: {str(kwargs['data'])[:300]}...")
                    if "cookies" in kwargs:
                        cookies_preview = {k: v[:10] + "..." if isinstance(v, str) and len(v) > 10 else v for k, v in
                                           kwargs['cookies'].items()}
                        logger.debug(f"{log_prefix} Cookies: {cookies_preview}")

            # Засекаем время выполнения
            start_time = time.perf_counter()

            try:
                # Выполняем обернутую функцию
                result = await func(*args, **kwargs)
                duration = round(time.perf_counter() - start_time, 2)

                # Логирование успешного выполнения
                if debug:
                    log_prefix = f"[{method}] {url}"  # Префикс для лога
                    logger.debug(f"{log_prefix} — успех за {duration}s")
                    try:
                        log_msg = f"{log_prefix} Результат: "
                        if isinstance(result, dict):
                            # Если это результат от HTTPXClient.fetch
                            if 'status_code' in result and 'json' in result:
                                json_data = result.get('json')
                                preview = str(json_data)[:500] if json_data is not None else 'None'
                                log_msg += f"HTTP Status: {result['status_code']}, JSON Preview: {preview}"
                                if len(str(json_data)) > 500: log_msg += "..."
                            # Если это другой словарь (например, от process_getting_code)
                            else:
                                preview = str(result)[:500]
                                log_msg += f"Dict Preview: {preview}"
                                if len(str(result)) > 500: log_msg += "..."
                        # Если результат - строка (например, от get_fias_api_token)
                        elif isinstance(result, str):
                            preview = result[:500]
                            log_msg += f"String Preview: '{preview}'"
                            if len(result) > 500: log_msg += "..."
                        # Если результат - None
                        elif result is None:
                            log_msg += "None"
                        # Другие типы
                        else:
                            preview = str(result)[:500]
                            log_msg += f"{type(result).__name__} Preview: {preview}"
                            if len(str(result)) > 500: log_msg += "..."

                        logger.debug(log_msg)

                    except Exception as log_ex:
                        logger.warning(f"{log_prefix} Не удалось залогировать результат: {log_ex}")

                return result

            except HTTPException as e:
                # Логируем HTTP-ошибки и пробрасываем дальше
                logger.warning(f"[HTTPX] {method} {url} — HTTP ошибка: {e.status_code} - {e.detail}")
                raise

            except Exception as e:
                # Обработка непредвиденных ошибок
                duration = round(time.perf_counter() - start_time, 2)

                # Вытаскиваем строку, где упало
                tb = traceback.extract_tb(e.__traceback__)
                last_frame = tb[-1] if tb else None
                lineno = last_frame.lineno if last_frame else "?"

                logger.error(
                    f"[HTTPX] ❌ Ошибка в {func_name} (строка {lineno}) — {method} {url} за {duration}s: {e}"
                )

                if debug:
                    logger.debug("Трейс:\n" + "".join(traceback.format_tb(e.__traceback__)))

                # Пробрасываем ошибку как HTTPException
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ошибка в {func_name} (строка {lineno}) при запросе {method} {url}: {str(e)}"
                )
        return wrapper
    return decorator


def route_handler(debug: bool = True, custom_errors: Dict[Type[Exception], int] = None) -> Callable[
    ..., Awaitable[Any]]:
    """Декоратор для логирования и обработки ошибок в роутах FastAPI.

    Логирует выполнение роута и обрабатывает исключения с кастомными статус-кодами.

    Args:
        debug (bool): Включает подробное логирование аргументов, результата и трейсов.
        custom_errors (Dict[Type[Exception], int], optional): Словарь исключений и соответствующих статус-кодов.

    Returns:
        Callable[..., Awaitable[Any]]: Обернутая функция.

    Example:
        ```python
        @route_handler(debug=True, custom_errors={ValueError: 400})
        async def my_route(request: Request):
            raise ValueError("Неверные данные")
        ```
    """
    # Список стандартных ошибок с соответствующими HTTP-статусами
    DEFAULT_CUSTOM_ERRORS = {
        ValueError: status.HTTP_400_BAD_REQUEST,                # Невалидные данные
        TypeError: status.HTTP_400_BAD_REQUEST,                 # Неправильный тип
        KeyError: status.HTTP_400_BAD_REQUEST,                  # Отсутствие ключа
        IndexError: status.HTTP_400_BAD_REQUEST,                # Выход за пределы списка
        AttributeError: status.HTTP_400_BAD_REQUEST,            # Обращение к несуществующему атрибуту
        PermissionError: status.HTTP_403_FORBIDDEN,             # Нет прав
        FileNotFoundError: status.HTTP_404_NOT_FOUND,           # Ресурс не найден
        TimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,          # Таймаут
        ConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,   # Ошибка соединения
        NotImplementedError: status.HTTP_501_NOT_IMPLEMENTED,   # Не реализовано
    }
    # Объединяем стандартные ошибки с пользовательскими, если они есть
    effective_errors = DEFAULT_CUSTOM_ERRORS.copy()
    if custom_errors:
        effective_errors.update(custom_errors)

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Извлекаем данные запроса или используем заглушки
            request = kwargs.get("request", None)
            func_name = func.__name__
            route_path = request.url.path if isinstance(request, Request) else func_name
            method = request.method if isinstance(request, Request) else "N/A"
            # Логирование перед выполнением роута
            if debug:
                logger.debug(f"[ROUTE] {method} {route_path} — старт")
                if args:
                    logger.debug(f"[ROUTE] args: {str(args)[:300]}")
                if kwargs:
                    kwargs_preview = {k: str(v)[:50] + "..." if isinstance(v, str) and len(str(v)) > 50 else v for k, v
                                      in kwargs.items()}
                    logger.debug(f"[ROUTE] kwargs: {kwargs_preview}")

            # Засекаем время выполнения
            start_time = time.perf_counter()

            try:
                # Выполняем роут
                result = await func(*args, **kwargs)
                duration = round(time.perf_counter() - start_time, 2)
                # Логирование успешного выполнения
                if debug:
                    logger.debug(f"[ROUTE] {method} {route_path} — успех за {duration}s")
                    result_info = f"type={type(result).__name__}, len={len(result) if hasattr(result, '__len__') else 'N/A'}"
                    logger.debug(f"[ROUTE] результат: {result_info}")
                return result

            except HTTPException as e:
                # Логируем HTTP-ошибки и пробрасываем дальше
                logger.warning(f"[ROUTE] {method} {route_path} — HTTP ошибка: {e.status_code} - {e.detail}")
                raise

            except Exception as e:
                # Обработка непредвиденных ошибок
                duration = round(time.perf_counter() - start_time, 2)
                tb = traceback.extract_tb(e.__traceback__)
                last_frame = tb[-1] if tb else None
                lineno = last_frame.lineno if last_frame else "?"
                logger.error(
                    f"[ROUTE] ❌ Ошибка в {func_name} (строка {lineno}) — {method} {route_path} за {duration}s: {e}")
                if debug:
                    logger.debug(f"[ROUTE] Трейс:\n{''.join(traceback.format_tb(e.__traceback__))[:1000]}")

                # Пробрасываем ошибку с соответствующим статус-кодом
                status_code = effective_errors.get(type(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
                raise HTTPException(
                    status_code=status_code,
                    detail=str(e)
                )
        return wrapper
    return decorator
