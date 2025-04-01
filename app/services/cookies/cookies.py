import json
from pathlib import Path

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.httpx_client import HTTPXClient
from app.core.logger import logger

settings = get_settings()

COOKIES_FILE = Path(settings.COOKIES_FILE)
BASE_URL = settings.BASE_URL


async def get_new():
    cookies = {}
    try:
        # get first part of cookies
        url = BASE_URL
        params = {"c": "portal", "m": "promed", "from": "promed"}
        response = await HTTPXClient.fetch(url=url, method="GET", params=params)
        cookies.update(response.get('cookies', {}))

        # authorize
        url = BASE_URL
        params = {"c": "main", "m": "index", "method": "Logon"}
        data = {"login": settings.EVMIAS_LOGIN, "psw": settings.EVMIAS_PASSWORD}
        response = await HTTPXClient.fetch(url=url, method="POST", cookies=cookies, params=params, data=data)

        if response["status_code"] != 200 or "true" not in response["text"]:
            raise HTTPException(status_code=401, detail="Authorization failed")

        cookies["login"] = settings.EVMIAS_LOGIN
        logger.info("Authorization success")

        # if response["status_code"] == 200 and response.get("json") == {"success": True}:
        #     logger.info("Authorization success")
        # else:
        #     logger.error("Authorization failed")
        #     raise RuntimeError("Authorization failed")
        #
        # cookies["login"] = settings.EVMIAS_LOGIN

        # get second part of cookies
        url = f"{BASE_URL}ermp/servlets/dispatch.servlet"
        headers = {
            "Content-Type": "text/x-gwt-rpc; charset=utf-8",
            "X-Gwt-Permutation": settings.EVMIAS_PERMUTATION,
            "X-Gwt-Module-Base": "https://evmias.fmba.gov.ru/ermp/",
        }
        data = settings.EVMIAS_SECRET
        response = await HTTPXClient.fetch(url=url, method="POST", headers=headers, cookies=cookies, data=data)

        if response["status_code"] != 200:
            logger.error(f"Error getting final cookies: {response['status_code']}")
            raise HTTPException(status_code=400, detail="Error getting final cookies")

        # if response["status_code"] != 200:
        #     logger.error(f"Error getting final cookies: {response['status_code']}")
        #     raise RuntimeError(f"Error getting final cookies: {response['status_code']}")

        cookies.update(response.get('cookies', {}))
        logger.info("Final cookies received successfully")

        # save cookies in file
        logger.info(f"Saving cookies to {COOKIES_FILE}")
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with COOKIES_FILE.open("w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False)
        logger.info("Cookies saved successfully")

    except Exception as e:
        logger.error(f"Error getting cookies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting cookies")
    return cookies


async def check_existing() -> bool:
    if not COOKIES_FILE.exists():
        logger.info(f"Cookies file not found: {COOKIES_FILE}")
        return False

    try:
        content = COOKIES_FILE.read_text(encoding="utf-8")
        cookies = json.loads(content)
        if not isinstance(cookies, dict):
            raise ValueError("Invalid cookies format")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Reading cookies file error: {e}")
        return False

    logger.info("Checking existing cookies")

    url = settings.BASE_URL
    params = {"c": "Common", "m": "getCurrentDateTime"}
    data = {"is_activerules": "true"}

    try:
        response = await HTTPXClient.fetch(url=url, method="POST", params=params, cookies=cookies, data=data)
        if response["status_code"] == 200 and response["json"]:
            return True
        logger.error("Cookies not valid")
        return False
    except Exception as e:
        logger.error(f"Error checking cookies: {e}")
        return False


async def load_cookies() -> dict:
    if not COOKIES_FILE.exists():
        logger.info(f"Cookies file not found: {COOKIES_FILE}")
        return {}

    try:
        content = COOKIES_FILE.read_text(encoding="utf-8")
        cookies = json.loads(content)
        if not isinstance(cookies, dict):
            raise ValueError("Invalid cookies format")
        logger.info(f"Cookies loaded from {COOKIES_FILE}")
        return cookies
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Error reading cookies file: {e}")
        return {}


async def set_cookies() -> dict | None:
    try:
        if await check_existing():
            logger.info("Current cookies are valid")
            cookies = await load_cookies()
            if not cookies:
                logger.error("No valid cookies found, getting new ones...")
                cookies = await get_new()
        else:
            logger.info("Current cookies are invalid, getting new ones..")
            cookies = await get_new()

        return cookies or None
    except HTTPException as e:
        raise
    except Exception as e:
        logger.debug(f"Error setting cookies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error setting cookies")
        # return None
