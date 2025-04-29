from fastapi import status, HTTPException
from httpx import HTTPStatusError, RequestError

from app.core import logger, get_settings
from app.models import Event

settings = get_settings()


async def get_polis_id(cookies, http_service, event: Event):
    url = settings.BASE_URL
    headers = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}

    params = {"c": "Person", "m": "getPersonEditWindow"}

    data = {
        "person_id": event.service.person_id,
        "server_id": event.service.server_id,
        "attrObjects": "true",
        "mode": [{"object": "PersonEditWindow", "identField": "Person_id"}],
    }

    try:
        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
            raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
        )

        # Проверяем, что ответ не пустой и содержит данные
        json_response = response.get('json')
        if not json_response or not isinstance(json_response, list) or len(json_response) == 0:
            logger.error(f"Ответ на запрос id полиса пустой или имеет неверный формат.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Некорректный ответ от ЕВМИАС на запрос id полиса"
            )

        raw_data = json_response[0]

        # --- обогащаем event модель данными из ответа ---
        event.insurance.polis_type_id = raw_data.get("PolisType_id", None)

        return event

    except (HTTPStatusError, RequestError) as e:
        # Эти ошибки уже обработаны в HTTPXClient и/или будут пойманы декоратором @route_handler,
        # который преобразует их в 502, 503, 504 и т.д.
        logger.error(f"Ошибка запроса id полиса: {e}")
        raise  # Пробрасываем ошибку, чтобы декоратор ее поймал

    except HTTPException as e:  # Пробрасываем HTTPException, созданную выше при проверке ответа
        raise

    except Exception as e:
        # Ловим остальные ошибки (валидация, парсинг, структура) здесь для логирования
        logger.error(f"Ошибка обработки ответа для полис id: {e}", exc_info=True)
        # Пробрасываем дальше, декоратор превратит в 500/400
        raise