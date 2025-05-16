from typing import Optional

from fastapi import status, HTTPException
from httpx import HTTPStatusError, RequestError

from app.core import HTTPXClient, get_settings, logger, HandbooksStorage
# маппер направивших на госпитализацию медицинских организаций, которые нельзя однозначно получить из справочника
from app.core.mappings import referred_org_map
from app.models import Event

# константы для описания источника направления
REFERRED_BY_OTHER_MO = "2"
REFERRED_BY_SAME_MO = "1"

settings = get_settings()
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}


async def _get_raw_referred_data(event_id: str, cookies: dict[str, str], http_service: HTTPXClient) -> dict[str, str]:
    # получаем данные о направлении на госпитализацию в виде словаря и возвращаем
    url = BASE_URL
    headers = HEADERS
    params = {"c": "EvnPS", "m": "loadEvnPSEditForm"}
    data = {
        "EvnPS_id": event_id,
        "archiveRecord": "0",
        "delDocsView": "0",
        "attrObjects": [{"object": "EvnPSEditWindow", "identField": "EvnPS_id"}],
    }

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
    return json_response[0]


async def _get_and_set_referral_date(event: Event, raw_referred_data: dict[str, str]) -> None:
    # получаем дату направления и добавляем ее к сведениям о госпитализации
    referral_date: Optional[str] = raw_referred_data.get("EvnDirection_setDate")
    if referral_date:
        event.referral.date = referral_date
    else:
        logger.error(
            f"Ответ на запрос направления на госпитализацию {event.service.event_id} не содержит дату направления.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ответ на запрос направления на госпитализацию не содержит дату направления."
                   f"Событие {event.service.event_id}"
        )


async def _get_and_set_referral_type_name(
        event: Event,
        handbooks_storage: HandbooksStorage,
        referral_type_id: str
) -> None:
    # получаем тип направившего на госпитализацию и добавляем его к сведениям о госпитализации
    referral_type = handbooks_storage.handbooks.get("referred_by")
    if referral_type:
        referral_type_data = referral_type.get(referral_type_id)
        if referral_type_data:
            event.referral.who_direct = referral_type_data.get("name")
        else:
            logger.warning(f"Не удалось определить тип направившего на госпитализацию id: {referral_type_id}")
    else:
        logger.error(f"Не удалось получить справочник 'referred_by'")


async def enrich_event_hospital_referral(
        event: Event,
        handbooks_storage: HandbooksStorage,
        cookies: dict[str, str],
        http_service: HTTPXClient,
) -> Event:
    """ Дополняет сведения о госпитализации сведениями о направлении на госпитализацию"""
    event_id = event.service.event_id
    try:
        raw_referred_data = await _get_raw_referred_data(event_id, cookies, http_service)
        await _get_and_set_referral_date(event, raw_referred_data)

        # получаем id кем направлен (другая МО или сама МО)
        referral_type_id = str(raw_referred_data.get("PrehospDirect_id", None))
        await _get_and_set_referral_type_name(event, handbooks_storage, referral_type_id)

        referred_org_id = raw_referred_data.get("Org_did")
        # справочник направивших на госпитализацию организаций (ЕВМИАС)
        referred_data = handbooks_storage.handbooks.get("referred_organizations").get(referred_org_id)
        # справочник МО (от фонда)
        medical_organizations = handbooks_storage.handbooks.get("medical_organizations").get("data")

        org_evmias_name = referred_data.get("name")
        org_evmias_token = referred_data.get("token")

        # если направила другая МО
        if referral_type_id == REFERRED_BY_OTHER_MO:
            map_keys = referred_org_map.keys()
            handbook_keys = medical_organizations.keys()

            if org_evmias_name in map_keys:
                org_map = referred_org_map.get(org_evmias_name)
                event.referral.who_direct = referred_by_name
                event.referral.org_name = org_map.get("name")
                event.referral.org_nick = org_map.get("nick")
                event.referral.org_code = org_map.get("code")[0:8]
                event.referral.org_token = org_map.get("token")

            elif (org_evmias_name not in map_keys) and (org_evmias_token in handbook_keys):
                org_handbook = medical_organizations.get(org_evmias_token)[0]
                event.referral.who_direct = referred_by_name
                event.referral.org_name = org_handbook.get("NAM_MOP")
                event.referral.org_nick = org_handbook.get("NAM_MOK")
                event.referral.org_code = org_handbook.get("IDMO")[0:8]
                event.referral.org_token = org_evmias_token

            else:
                logger.warning(
                    f"Не удалось найти справочную информацию о направившей организации: "
                    f"{org_evmias_name} ({org_evmias_token}).")

        # todo: если направила сама МО

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
