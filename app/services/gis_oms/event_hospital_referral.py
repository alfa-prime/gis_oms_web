from httpx import HTTPStatusError, RequestError
from fastapi import status, HTTPException
from app.core import HTTPXClient, get_settings, logger, HandbooksStorage
from app.models import Event
from app.services.handbooks.evmias import get_referred_by_handbook

settings = get_settings()
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}


async def enrich_event_hospital_referral(
        event: Event,
        handbooks_storage: HandbooksStorage,
        cookies: dict[str, str],
        http_service: HTTPXClient,
) -> Event:
    """ Дополняет сведения о госпитализации сведениями о направлении на госпитализацию"""
    event_id = event.service.event_id

    url = BASE_URL
    headers = HEADERS
    params = {"c": "EvnPS", "m": "loadEvnPSEditForm"}
    data = {
        "EvnPS_id": event_id,
        "archiveRecord": "0",
        "delDocsView": "0",
        "attrObjects": [{"object": "EvnPSEditWindow", "identField": "EvnPS_id"}],
    }
    try:
        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
        )

        json_response = response.get('json')
        if not json_response or not isinstance(json_response, list) or len(json_response) == 0:
            logger.error(f"Ответ loadEvnPSEditForm для события {event_id} пустой или имеет неверный формат.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Некорректный ответ от ЕВМИАС (loadEvnPSEditForm) для события {event_id}"
            )

        raw_referral_data = json_response[0]

        referred_by_id = raw_referral_data.get("PrehospDirect_id")
        referral_number = raw_referral_data.get("EvnDirection_Num")
        referral_date = raw_referral_data.get("EvnDirection_setDate")
        referral_org_evmias_id = raw_referral_data.get("Org_did")

        handbook_referred_by = handbooks_storage.handbooks.get("referred_by", None)
        referred_by = handbook_referred_by.get(referred_by_id, None)

        logger.debug(f"REFERRED_BY_ID: {referred_by}")

        return event

    except (HTTPStatusError, RequestError) as e:
        # Эти ошибки уже обработаны в HTTPXClient и/или будут пойманы декоратором @route_handler,
        # который преобразует их в 502, 503, 504 и т.д.
        logger.error(f"Ошибка запроса для события {event_id}: {e}")
        raise  # Пробрасываем ошибку, чтобы декоратор ее поймал

    except HTTPException as e:  # Пробрасываем HTTPException, созданную выше при проверке ответа
        raise

    except Exception as e:
        # Ловим остальные ошибки (валидация, парсинг, структура) здесь для логирования
        logger.error(f"Ошибка обработки ответа для события {event_id}: {e}", exc_info=True)
        # Пробрасываем дальше, декоратор превратит в 500/400
        raise
