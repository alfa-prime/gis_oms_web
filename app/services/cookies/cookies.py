import json
import aiofiles
from aiopath import AsyncPath

from fastapi import HTTPException, Depends
from httpx import HTTPStatusError, TimeoutException

from app.core import get_settings, HTTPXClient, get_http_service, logger

settings = get_settings()

# Путь к файлу с cookies
COOKIES_FILE: AsyncPath = AsyncPath(settings.COOKIES_FILE)
# Базовый URL для запросов к внешнему сервису
BASE_URL = settings.BASE_URL


async def read_cookies_file() -> dict:
    """Читает cookies из файла и возвращает их в виде словаря.
        Returns:
            dict: Словарь с cookies или пустой словарь, если файла нет или данные некорректны.
    """
    if not await COOKIES_FILE.exists():
        logger.info(f"Файл с cookies не найден: {COOKIES_FILE}")
        return {}
    try:
        content = await COOKIES_FILE.read_text(encoding="utf-8")
        cookies = json.loads(content)
        if not isinstance(cookies, dict):
            raise ValueError("Неверный формат cookies")
        logger.info(f"Сookies успешно загружены из файла {COOKIES_FILE}")
        return cookies
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Ошибка чтения файла с cookies: {e}")
        return {}


async def fetch_initial_cookies(http_service: HTTPXClient) -> dict:
    """Получает первую часть cookies от внешнего сервиса.
       Returns:
           dict: Словарь с начальными cookies или пустой словарь, если их нет в ответе.
   """
    params = {"c": "portal", "m": "promed", "from": "promed"}
    response = await http_service.fetch(url=BASE_URL, method="GET", params=params)
    logger.info("Первая часть cookies получена успешно")
    return response.get('cookies', {})


async def authorize(cookies: dict, http_service: HTTPXClient) -> dict:
    """Авторизует пользователя на внешнем сервисе и добавляет логин в cookies.
    Args:
        cookies (dict): Начальные cookies, полученные от fetch_initial_cookies.
        http_service (HTTPXClient): Клиент HTTPX для выполнения запросов.
    Returns:
        dict: Обновленные cookies с добавленным логином.
    Raises:
        HTTPException: Если авторизация не удалась (статус != 200 или "true" нет в ответе).
    """
    params = {"c": "main", "m": "index", "method": "Logon"}
    # Данные для авторизации
    data = {"login": settings.EVMIAS_LOGIN, "psw": settings.EVMIAS_PASSWORD}
    response = await http_service.fetch(url=BASE_URL, method="POST", cookies=cookies, params=params, data=data)

    # Проверка успешности авторизации
    if response["status_code"] != 200 or "true" not in response["text"]:
        raise HTTPException(status_code=401, detail="Авторизация не удалась")

    # Добавляем логин в cookies
    cookies["login"] = settings.EVMIAS_LOGIN
    logger.info("Авторизация прошла успешно")
    return cookies


async def fetch_final_cookies(cookies: dict, http_service: HTTPXClient) -> dict:
    """Получает финальную часть cookies через POST-запрос к сервлету.
    Args:
        cookies (dict): Cookies после авторизации.
        http_service (HTTPXClient): Клиент HTTPX для выполнения запросов.
    Returns:
        dict: Обновленные cookies с финальными данными.
    Raises:
        HTTPException: Если запрос завершился с ошибкой (статус != 200).
    """
    url = f"{BASE_URL}ermp/servlets/dispatch.servlet"
    headers = {
        "Content-Type": "text/x-gwt-rpc; charset=utf-8",
        "X-Gwt-Permutation": settings.EVMIAS_PERMUTATION,
        "X-Gwt-Module-Base": "https://evmias.fmba.gov.ru/ermp/",
    }
    # Секретные данные для запроса
    data = settings.EVMIAS_SECRET
    response = await http_service.fetch(url=url, method="POST", headers=headers, cookies=cookies, data=data)

    # Проверка успешности запроса
    if response["status_code"] != 200:
        logger.error(f"Ошибка получения второй части cookies: {response['status_code']}")
        raise HTTPException(status_code=400, detail="Ошибка получения второй части cookies")

    # Обновляем cookies из ответа
    cookies.update(response.get('cookies', {}))
    logger.info("Вторая часть cookies получена")
    return cookies


async def get_new(http_service: HTTPXClient):
    """Получает новые cookies через последовательные запросы и сохраняет их в файл.
       Returns:
           dict: Новые cookies.
       Raises:
           HTTPException: В случае ошибок HTTP, таймаута, записи файла или непредвиденных исключений.
       """
    try:
        # Последовательное получение cookies
        cookies = await fetch_initial_cookies(http_service)
        cookies = await authorize(cookies, http_service)
        cookies = await fetch_final_cookies(cookies, http_service)

        # Сохранение cookies в файл
        logger.info(f"Сохранение cookies в файл {COOKIES_FILE}")
        await COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(COOKIES_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(cookies, ensure_ascii=False, indent=4))
        logger.info(f"Сookies сохранены в файл {COOKIES_FILE}")
        return cookies

    except HTTPStatusError as e:
        logger.error(f"HTTP ошибка при получении cookies: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))

    except TimeoutException:
        logger.error("Превышено время ожидания запроса при получении cookies")
        raise HTTPException(status_code=504, detail="Превышено время ожидания запроса")

    except OSError as e:
        logger.error(f"Ошибка при сохранении кук в файл: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при сохранении cookies в файл")

    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении кук: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Неожиданная ошибка при получении cookies")


async def check_existing(http_service: HTTPXClient) -> bool:
    """Проверяет, действительны ли существующие cookies.
        Returns:
            bool: True, если cookies валидны, иначе False.
    """
    cookies = await read_cookies_file()
    if not cookies:
        return False

    params = {"c": "Common", "m": "getCurrentDateTime"}
    data = {"is_activerules": "true"}

    try:
        response = await http_service.fetch(url=BASE_URL, method="POST", params=params, cookies=cookies, data=data)
        # Проверка: если статус 200 и есть JSON-ответ, cookies считаются валидными
        if response["status_code"] == 200 and response["json"]:
            logger.info("Сookies действительны")
            return True
        logger.error("Сookies недействительны")
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке существующих cookies: {e}")
        return False


async def load_cookies() -> dict:
    """Загружает cookies из файла.
       Returns:
           dict: Словарь с cookies или пустой словарь, если загрузка не удалась.
   """
    return await read_cookies_file()


async def set_cookies(http_service: HTTPXClient = Depends(get_http_service)) -> dict:
    """Устанавливает cookies: использует существующие, если они валидны, иначе получает новые.
    Returns:
        dict: Действующие cookies.
    Raises:
        HTTPException: Если произошла ошибка при получении или проверке cookies.
    """
    try:
        if await check_existing(http_service):
            logger.info("Текущие cookies действительны")
            cookies = await load_cookies()
            if not cookies:
                logger.error("Текущие cookies недействительны, получаем новые.")
                cookies = await get_new(http_service)
        else:
            logger.info("Текущие cookies недействительны, получаем новые.")
            cookies = await get_new(http_service)

        return cookies
    except HTTPException as e:
        raise
    except Exception as e:
        logger.debug(f"Ошибка при установке кук: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка получения cookies")
