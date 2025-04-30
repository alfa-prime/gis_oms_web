import json
from typing import Annotated

import redis.asyncio as redis
from fastapi import HTTPException, Depends, status
from redis.exceptions import RedisError

from app.core import (
    get_settings,
    logger,
    get_http_service,
    HTTPXClient,
    get_redis_client
)

settings = get_settings()

# Базовый URL для запросов к внешнему сервису
BASE_URL = settings.BASE_URL


async def save_cookies_to_redis(redis_client: redis.Redis, cookies: dict):
    """Асинхронно сохраняет словарь с куками в Redis."""
    try:
        json_cookies = json.dumps(cookies, ensure_ascii=False)
        await redis_client.set(
            settings.REDIS_COOKIES_KEY,
            json_cookies,
            ex=settings.REDIS_COOKIES_TTL  # Устанавливаем TTL
        )
        logger.info(
            f"Куки успешно сохранены в Redis (ключ: '{settings.REDIS_COOKIES_KEY}', TTL: {settings.REDIS_COOKIES_TTL}s)"
        )
    except RedisError as e:
        logger.error(f"Ошибка Redis при сохранении кук: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка Redis при сохранении кук: {e}"
        )
    except Exception as e:  # Ловим и другие возможные ошибки (например, json.dumps)
        logger.error(f"Неожиданная ошибка при сохранении кук в Redis: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Неожиданная ошибка при сохранении кук в Redis: {e}"
        )


async def load_cookies_from_redis(redis_client: redis.Redis) -> dict:
    """Асинхронно загружает и парсит куки из Redis."""
    cookies = {}
    try:
        json_cookies_bytes = await redis_client.get(settings.REDIS_COOKIES_KEY)
        if json_cookies_bytes is None:
            logger.info(f"Куки не найдены в Redis (ключ: '{settings.REDIS_COOKIES_KEY}')")
            return {}

        # Декодируем и парсим JSON
        try:
            json_cookies_str = json_cookies_bytes.decode('utf-8')
            cookies = json.loads(json_cookies_str)
            if not isinstance(cookies, dict):
                logger.error(f"Неверный формат кук, загруженных из Redis (не словарь): {cookies}")
                return {}  # Возвращаем пустой словарь при неверном формате
            logger.info(f"Куки успешно загружены из Redis (ключ: '{settings.REDIS_COOKIES_KEY}')")
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.error(
                f"Ошибка декодирования/парсинга кук из Redis: {e}. Сырые данные (часть): {json_cookies_bytes[:100]}...")
            # Возможно, стоит удалить невалидный ключ из Redis?
            await redis_client.delete(settings.REDIS_COOKIES_KEY)
            return {}

    except RedisError as e:
        logger.error(f"Ошибка Redis при загрузке кук: {e}", exc_info=True)
        # При ошибке чтения возвращаем пустой словарь, как будто кук нет
        return {}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке кук из Redis: {e}", exc_info=True)
        return {}

    return cookies


async def fetch_initial_cookies(http_service: HTTPXClient) -> dict:
    """Получает первую часть cookies от внешнего сервиса."""
    params = {"c": "portal", "m": "promed", "from": "promed"}
    # Используем http_service, обработка ошибок внутри fetch
    response = await http_service.fetch(url=BASE_URL, method="GET", params=params, raise_for_status=False)
    if response["status_code"] != 200:
        logger.error(f"Не удалось получить начальные cookies, статус: {response['status_code']}")
        raise HTTPException(status_code=response["status_code"], detail="Не удалось получить начальные cookies")
    logger.info("Первая часть cookies получена успешно")
    return response.get('cookies', {})


async def authorize(cookies: dict, http_service: HTTPXClient) -> dict:
    """Авторизует пользователя и добавляет логин в cookies."""
    params = {"c": "main", "m": "index", "method": "Logon"}
    data = {"login": settings.EVMIAS_LOGIN, "psw": settings.EVMIAS_PASSWORD}
    # Используем http_service
    response = await http_service.fetch(
        url=BASE_URL,
        method="POST",
        cookies=cookies,
        params=params,
        data=data,
        raise_for_status=False
    )

    if response["status_code"] != 200 or "true" not in response.get("text", ""):
        logger.error(
            f"Авторизация в ЕВМИАС не удалась. "
            f"Статус: {response['status_code']}, "
            f"Ответ: {response.get('text', '')[:100]}..."
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Авторизация не удалась")

    new_cookies = cookies.copy()  # Работаем с копией
    new_cookies["login"] = settings.EVMIAS_LOGIN
    # Добавляем куки из ответа, если они есть
    new_cookies.update(response.get('cookies', {}))
    logger.info("Авторизация прошла успешно")
    return new_cookies


async def fetch_final_cookies(cookies: dict, http_service: HTTPXClient) -> dict:
    """Получает финальную часть cookies через POST-запрос к сервлету."""
    url = f"{BASE_URL}ermp/servlets/dispatch.servlet"
    headers = {
        "Content-Type": "text/x-gwt-rpc; charset=utf-8",
        "X-Gwt-Permutation": settings.EVMIAS_PERMUTATION,
        "X-Gwt-Module-Base": "https://evmias.fmba.gov.ru/ermp/",
    }
    data = settings.EVMIAS_SECRET
    # Используем http_service
    response = await http_service.fetch(
        url=url,
        method="POST",
        headers=headers,
        cookies=cookies,
        data=data,
        raise_for_status=False
    )

    if response["status_code"] != 200:
        logger.error(f"Ошибка получения второй части cookies: {response['status_code']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ошибка получения второй части cookies от ЕВМИАС"
        )

    final_cookies = cookies.copy()
    final_cookies.update(response.get('cookies', {}))
    logger.info("Вторая часть cookies получена")
    return final_cookies


# --- Функция для получения новых cookies (объединяет шаги и сохраняет в Redis) ---
async def get_new_cookies(http_service: HTTPXClient, redis_client: redis.Redis) -> dict:
    """
    Получает НОВЫЕ cookies через последовательные запросы и сохраняет их в Redis.
    Выбрасывает HTTPException при ошибках взаимодействия с ЕВМИАС или Redis.
    """
    try:
        logger.info("Начинаем процесс получения новых cookies...")
        initial_cookies = await fetch_initial_cookies(http_service)
        authorized_cookies = await authorize(initial_cookies, http_service)
        final_cookies = await fetch_final_cookies(authorized_cookies, http_service)

        # Сохраняем финальные cookies в Redis
        await save_cookies_to_redis(redis_client, final_cookies)

        return final_cookies

    except HTTPException as e:
        # Пробрасываем HTTP ошибки, возникшие на шагах выше
        logger.error(f"HTTP ошибка во время получения новых cookies: {e.detail}")
        raise e
    except RedisError as e:  # Ловим ошибки Redis при сохранении
        logger.error(f"Ошибка Redis при сохранении новых cookies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка сохранения сессии (Redis)"
        )
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении новых кук: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Неожиданная ошибка при получении сессии"
        )


# --- Функция для проверки существующих кук (теперь из Redis) ---

async def check_existing_cookies(redis_client: redis.Redis, http_service: HTTPXClient) -> bool:
    """Проверяет, действительны ли cookies, хранящиеся в Redis."""
    cookies = await load_cookies_from_redis(redis_client)
    if not cookies:
        logger.info("cookies для проверки не найдены в Redis.")
        return False

    params = {"c": "Common", "m": "getCurrentDateTime"}
    data = {"is_activerules": "true"}

    try:
        # Используем http_service с текущими куками
        response = await http_service.fetch(
            url=BASE_URL,
            method="POST",
            params=params,
            cookies=cookies,
            data=data,
            raise_for_status=False
        )

        if response["status_code"] == 200 and response.get("json") is not None:
            logger.info("Проверка существующих cookies: Успешно (валидны)")
            return True
        else:
            logger.warning(
                f"Проверка существующих cookies: Невалидны (Статус: {response['status_code']}, "
                f"JSON: {response.get('json') is not None})"
            )
            return False
    except HTTPException as e:
        # Ошибки сети/сервера при проверке кук означают, что мы не можем их валидировать
        logger.warning(
            f"Ошибка при проверке существующих cookies ({type(e).__name__}): {e.detail}. "
            f"Считаем cookies невалидными."
        )
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке существующих cookies: {e}", exc_info=True)
        return False  # Считаем невалидными при любой ошибке проверки


async def set_cookies(
        # Внедряем зависимости через Annotated
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        redis_client: Annotated[redis.Redis, Depends(get_redis_client)]
) -> dict:
    """
    Основная FastAPI зависимость для получения действительных cookies.
    Проверяет cookies из Redis, если они невалидны или отсутствуют - получает новые.
    Возвращает словарь с действительными cookies.
    Выбрасывает HTTPException при невозможности получить/обновить cookies.
    """
    try:
        # Передаем зависимости явно в check_existing_cookies
        if await check_existing_cookies(redis_client=redis_client, http_service=http_service):
            logger.debug("Используем существующие валидные cookies из Redis.")
            # Передаем зависимость явно в load_cookies_from_redis
            cookies = await load_cookies_from_redis(redis_client=redis_client)
            # Доп. проверка на случай, если cookies исчезли между проверкой и загрузкой
            if not cookies:
                logger.warning("cookies исчезли из Redis после проверки валидности. Получаем новые.")
                cookies = await get_new_cookies(http_service=http_service, redis_client=redis_client)
        else:
            logger.info("Существующие cookies невалидны или отсутствуют. Получаем новые.")
            # Передаем зависимости явно в get_new_cookies
            cookies = await get_new_cookies(http_service=http_service, redis_client=redis_client)

        if not cookies:
            # Эта ситуация не должна произойти, если get_new_cookies работает правильно
            logger.critical("Не удалось получить или загрузить cookies после всех попыток!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось установить сессию ЕВМИАС"
            )

        return cookies

    except HTTPException as e:
        # Пробрасываем HTTP ошибки, которые могли возникнуть в check_existing или get_new
        raise e
    except Exception as e:
        # Ловим остальные неожиданные ошибки на этом уровне
        logger.critical(f"Критическая ошибка в set_cookies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка при управлении сессией"
        )
