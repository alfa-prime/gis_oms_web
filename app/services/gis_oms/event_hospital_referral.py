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

        # получили данные о направлении на госпитализацию в виде словаря
        raw_referred_data = json_response[0]
        # получаем id кем направлен (другая МО или сама МО)
        referred_by_id = str(raw_referred_data.get("PrehospDirect_id", None))
        referred_org_id = raw_referred_data.get("Org_did")

        # справочник направивших на госпитализацию организаций (ЕВМИАС)
        referred_data = handbooks_storage.handbooks.get("referred_organizations").get(referred_org_id)
        # справочник МО (от фонда)
        medical_organizations = handbooks_storage.handbooks.get("medical_organizations").get("data")

        org_evmias_name = referred_data.get("name")
        org_evmias_token = referred_data.get("token")

        # если направила другая МО
        if referred_by_id == REFERRED_BY_OTHER_MO:
            map_keys = referred_org_map.keys()
            handbook_keys = medical_organizations.keys()

            if org_evmias_name in map_keys:
                org_map = referred_org_map.get(org_evmias_name)
                org_name = org_map.get("name")
                org_nick = org_map.get("nick")
                org_token = org_map.get("token")
                org_code = org_map.get("code")[0:8]

            elif (org_evmias_name not in map_keys) and (org_evmias_token in handbook_keys):
                org_handbook = medical_organizations.get(org_evmias_token)[0]
                org_name = org_handbook.get("NAM_MOP")
                org_nick = org_handbook.get("NAM_MOK")
                org_code = org_handbook.get("IDMO")
                org_token = org_evmias_token

            else:
                logger.warning(
                    f"Не удалось найти справочную информацию о направившей организации: "
                    f"{org_evmias_name} ({org_evmias_token}).")

        # todo: удалить после отладки
        logger.debug(f"org_name: {org_name}, org_nick: {org_nick}, org_token: {org_token}, org_code: {org_code}")

        # todo: добавить эти сведения в event
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
