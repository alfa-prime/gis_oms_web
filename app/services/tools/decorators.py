import functools
import traceback
import time
from typing import Callable, Awaitable, Any, Type, Dict
from fastapi import HTTPException, status, Request
from app.core.logger import logger


def log_and_catch(debug: bool = True) -> Callable[..., Awaitable[Any]]:
    """
    Универсальный декоратор для логгирования и перехвата ошибок в асинхронных функциях (например, HTTP-запросах).
    :param debug: Включает подробное логгирование параметров и трейса.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            method = kwargs.get("method", "GET")
            url = kwargs.get("url", "UNKNOWN_URL")
            func_name = func.__name__

            # Лог до вызова функции (если debug включён)
            if debug:
                logger.debug(f"[HTTPX] {method} {url} — старт")
                if "params" in kwargs:
                    params_preview = str(kwargs['params'])[:300]
                    logger.debug(f"[HTTPX] params: {params_preview}")
                if "data" in kwargs:
                    data_preview = str(kwargs['data'])[:300]
                    logger.debug(f"[HTTPX] data: {data_preview}")
                if "cookies" in kwargs:
                    cookies_preview = {
                        k: v[:10] + "..." if isinstance(v, str) and len(v) > 10 else v
                        for k, v in kwargs['cookies'].items()
                    }
                    logger.debug(f"[HTTPX] cookies: {cookies_preview}")

            start_time = time.perf_counter()

            try:
                # Выполнение функции
                result = await func(*args, **kwargs)
                duration = round(time.perf_counter() - start_time, 2)

                if debug:
                    logger.debug(f"[HTTPX] {method} {url} — успех за {duration}s")
                    logger.debug(f"[HTTPX] ответ (обрезан): {str(result.get('text', ''))[:500]}")

                return result

            except HTTPException as e:
                logger.warning(f"[HTTPX] {method} {url} — HTTP ошибка: {e.status_code} - {e.detail}")
                raise

            except Exception as e:
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

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Ошибка в {func_name} (строка {lineno}) при запросе {method} {url}: {str(e)}"
                )

        return wrapper

    return decorator


def route_handler(debug: bool = True, custom_errors: Dict[Type[Exception], int] = None) -> Callable[..., Awaitable[Any]]:
    """
    Декоратор для обработки ошибок и логирования в роутах FastAPI.
    :param debug: Включает подробное логгирование аргументов, результата и трейса ошибок.
    :param custom_errors: Словарь {тип_ошибки: статус-код} для кастомной обработки исключений.
    """
    # Сокращённый список стандартных ошибок
    DEFAULT_CUSTOM_ERRORS = {
        ValueError: status.HTTP_400_BAD_REQUEST,        # Невалидные данные
        TypeError: status.HTTP_400_BAD_REQUEST,         # Неправильный тип
        KeyError: status.HTTP_400_BAD_REQUEST,          # Отсутствие ключа
        IndexError: status.HTTP_400_BAD_REQUEST,        # Выход за пределы списка
        AttributeError: status.HTTP_400_BAD_REQUEST,    # Обращение к несуществующему атрибуту
        PermissionError: status.HTTP_403_FORBIDDEN,     # Нет прав
        FileNotFoundError: status.HTTP_404_NOT_FOUND,   # Ресурс не найден
        TimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,  # Таймаут
        ConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,  # Ошибка соединения
        NotImplementedError: status.HTTP_501_NOT_IMPLEMENTED,  # Не реализовано
    }

    effective_errors = DEFAULT_CUSTOM_ERRORS.copy()
    if custom_errors:
        effective_errors.update(custom_errors)

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request", None)
            func_name = func.__name__
            route_path = request.url.path if isinstance(request, Request) else func_name
            method = request.method if isinstance(request, Request) else "N/A"

            if debug:
                logger.debug(f"[ROUTE] {method} {route_path} — старт")
                if args:
                    logger.debug(f"[ROUTE] args: {str(args)[:300]}")
                if kwargs:
                    kwargs_preview = {k: str(v)[:50] + "..." if isinstance(v, str) and len(str(v)) > 50 else v for k, v in kwargs.items()}
                    logger.debug(f"[ROUTE] kwargs: {kwargs_preview}")

            start_time = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                duration = round(time.perf_counter() - start_time, 2)
                if debug:
                    logger.debug(f"[ROUTE] {method} {route_path} — успех за {duration}s")
                    result_info = f"type={type(result).__name__}, len={len(result) if hasattr(result, '__len__') else 'N/A'}"
                    logger.debug(f"[ROUTE] результат: {result_info}")
                return result

            except HTTPException as e:
                logger.warning(f"[ROUTE] {method} {route_path} — HTTP ошибка: {e.status_code} - {e.detail}")
                raise

            except Exception as e:
                duration = round(time.perf_counter() - start_time, 2)
                tb = traceback.extract_tb(e.__traceback__)
                last_frame = tb[-1] if tb else None
                lineno = last_frame.lineno if last_frame else "?"
                logger.error(f"[ROUTE] ❌ Ошибка в {func_name} (строка {lineno}) — {method} {route_path} за {duration}s: {e}")
                if debug:
                    logger.debug(f"[ROUTE] Трейс:\n{''.join(traceback.format_tb(e.__traceback__))[:1000]}")

                status_code = effective_errors.get(type(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
                raise HTTPException(
                    status_code=status_code,
                    detail=str(e)
                )

        return wrapper
    return decorator


