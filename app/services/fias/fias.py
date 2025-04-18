"""
Сервис для взаимодействия с АПИ ФИАС (https://fias-public-service.nalog.ru/api/spas/v2.0/swagger/index.html).
для получения кодов ОКАТО
"""
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status

from app.core import HTTPXClient, get_http_service, get_settings, logger
from app.core.decorators import log_and_catch

settings = get_settings()


@log_and_catch(debug=settings.DEBUG_HTTP)
async def get_fias_api_token(http_service: HTTPXClient) -> str:
    """Получение токена для доступа к АПИ"""
    url = settings.FIAS_TOKEN_URL
    params = {
        "url": "https://fias.nalog.ru/Search?objectId=0&addressType=2&fullName="
    }
    response = await http_service.fetch(
        url=url,
        method="GET",
        params=params,
        raise_for_status=True
    )

    try:
        token = response["json"]["Token"]
        if isinstance(token, str) and token:
            return token
        else:
            logger.error(f"Некорректное значение токена ФИАС: {token}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Некорректное значение токена ФИАС.")
    except (KeyError, TypeError) as e:
        logger.error(f"Ошибка извлечения токена ФИАС из ответа {response.get('json')}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось извлечь токен ФИАС из ответа.")


@log_and_catch(debug=settings.DEBUG_HTTP)
async def process_getting_code(
        address_string: str,
        api_token: str,
        http_service: HTTPXClient
) -> Optional[dict]:
    """
    Получение сведений по адресу из ФИАС.
    Возвращает словарь {'full_address': str, 'okato_code': str} или None.
    """
    url = f"{settings.FIAS_API_BASE_URL}/SearchAddressItem"
    headers = {
        "accept": "application/json",
        "master-token": api_token
    }

    params = {
        "search_string": address_string,
        "address_type": "1",
    }

    response = await http_service.fetch(
        url=url,
        method="GET",
        headers=headers,
        params=params,
        raise_for_status=False  # Оставляем False, чтобы самим обработать статусы ФИАС
    )

    if response["status_code"] != 200:
        logger.warning(f"ФИАС вернул статус {response['status_code']} для адреса '{address_string[:50]}...'")
        return None

    try:
        response_json = response["json"]
        okato_str = str(response_json["address_details"]["okato"])
        full_address = response_json.get("full_name")
        return {"full_address": full_address, "okato_code": okato_str}

    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(
            f"Ошибка парсинга ответа ФИАС для '{address_string[:50]}...'. Ошибка: {e}. Ответ: {response.get('json')}")
        return None


async def get_okato_code(
        address_string: str,
        http_service: Annotated[HTTPXClient, Depends(get_http_service)]
):
    """
    Получает код ОКАТО и полный адрес по адресу из ФИАС. Управляет получением токена.
    """
    try:
        # Подавляем ложное предупреждение PyCharm, т.к. get_fias_api_token - это awaitable wrapper
        # noinspection PyCallingNonCallable
        api_token = await get_fias_api_token(http_service)

        logger.debug(f"=== TOKEN ===: {api_token}")
        # noinspection PyCallingNonCallable
        answer = await process_getting_code(
            address_string,
            api_token,
            http_service
        )
        return answer
    except HTTPException as e:
        logger.error(f"Не удалось получить ОКАТО из-за ошибки получения токена ФИАС: {e.detail}")
        return None
    except Exception as e:  # Ловим неожиданные ошибки здесь
        logger.error(f"Неожиданная ошибка в get_okato_code для '{address_string[:50]}...': {e}", exc_info=True)
        return None
