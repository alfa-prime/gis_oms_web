import uuid
from datetime import datetime
from typing import Optional

from fastapi import status, HTTPException
from httpx import HTTPStatusError, RequestError

from app.core import HTTPXClient, get_settings, logger, HandbooksStorage
# маппер направивших на госпитализацию медицинских организаций, которые нельзя однозначно получить из справочника
from app.core.mappings import referred_org_map, current_org_map
from app.models import Event
from app.services import get_handbook_payload

# константы для описания источника направления
REFERRED_BY_OTHER_MO = "2"
REFERRED_BY_DEPARTMENT = "1"

settings = get_settings()


async def _get_raw_referred_data(event_id: str, cookies: dict[str, str], http_service: HTTPXClient) -> dict[str, str]:
    """
    Получает данные о госпитализации, путем выполнения запроса к ЕВМИАС, в виде словаря по id госпитализации
    """
    url = settings.BASE_URL
    headers = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
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
        logger.error(f"Event {event_id}: Запрос referred_data пустой или имеет неверный формат.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Некорректный ответ от ЕВМИАС (referred_data) для события {event_id}"
        )
    return json_response[0]


async def _get_and_set_referral_talon_date_and_number(event: Event, raw_referred_data: dict[str, str]) -> None:
    """
    Получает дату направления и номер талона из запроса к ЕВМИАС и добавляет их к сведениям о госпитализации
    """
    event_id = event.service.event_id
    referral_date: Optional[str] = raw_referred_data.get("EvnDirection_setDate")
    if referral_date:
        referral_date = datetime.strptime(referral_date, "%d.%m.%Y").strftime("%Y-%m-%d")
        event.referral.talon_date = referral_date
        # todo: подумать о значении по умолчанию, если номер талона отсутствует в системе ЕВМИАС
        event.referral.talon_number = raw_referred_data.get("EvnDirection_Num", '******')
    else:
        logger.error(f"Ответ на запрос направления на госпитализацию {event_id} не содержит дату направления.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Событие {event_id}: нет даты направления."
        )


async def _get_and_set_referral_type_name(event: Event, handbooks_storage: HandbooksStorage,
                                          referral_type_id: str) -> None:
    """
    Получает название типа (другая МО или отделение основной МО)
    направивших на госпитализацию из справочника и добавляет его к сведениям о госпитализации
    """
    event_id = event.service.event_id
    event.referral.who_direct = None

    if not referral_type_id or referral_type_id == "None":  # Явная проверка на отсутствие ID
        logger.info(
            f"Event {event_id}: ID типа направления отсутствует или 'None'. Имя типа не будет установлено.")
        return

    referral_type_handbook = get_handbook_payload(handbooks_storage, "referred_by", event_id)
    if isinstance(referral_type_handbook, dict):
        referral_type_entry = referral_type_handbook.get(referral_type_id)
        if isinstance(referral_type_entry, dict):  # Проверяем, что это словарь
            type_name = referral_type_entry.get("name")
            if type_name is not None:
                event.referral.who_direct = str(type_name)
            else:
                logger.warning(
                    f"Event {event_id}: В справочнике 'referred_by' для ID '{referral_type_id}' отсутствует поле 'name'.")
        else:
            logger.warning(
                f"Event {event_id}: Запись для ID типа '{referral_type_id}' не найдена в справочнике 'referred_by'.")
    else:
        logger.warning(f"Event {event_id}: Не удалось получить справочник 'referred_by'.")


async def _generate_referral_id_for_xml_unload(event: Event) -> None:
    """
    Генерирует уникальный идентификатор направления на госпитализацию, на основании id госпитализации в рамках ЕВМИАС,
    для дальнейшего использования при выгрузке в XML файл
    """
    namespace_evmias_referral_str = "2a4cf038-b340-44d7-8bbc-42a7241b6b8b"
    namespace_evmias_referral = uuid.UUID(namespace_evmias_referral_str)
    event_id = event.service.event_id
    event.referral.id = str(uuid.uuid5(namespace_evmias_referral, event_id))


async def _get_and_set_medical_care_condition(event: Event, handbooks_storage: HandbooksStorage, ) -> None:
    """
    Получает условие оказания медпомощи (стационар или дневной стационар)
    и добавляет соответствующий код из справочника фонда V006 к сведениям о направлении на госпитализацию
    """
    event_id = event.service.event_id
    condition: Optional[str] = None
    department_name = event.hospitalization.department_name.lower().strip()
    if department_name and department_name.startswith("дс"):
        condition = "В дневном стационаре"
    elif department_name:
        condition = "Стационарно"

    if not condition:
        logger.warning(
            f"Event {event_id}: Не удалось определить текстовое условие оказания медпомощи по department_name "
            f"('{event.hospitalization.department_name}') для события {event.service.event_id}")
        return

    try:
        medical_care_handbook = handbooks_storage.handbooks.get("medical_care_conditions", {}).get('data', {})
        condition_entry = medical_care_handbook.get(condition)

        if isinstance(condition_entry, list) and condition_entry:
            condition_detail = condition_entry[0]
            if isinstance(condition_detail, dict):
                condition_id = condition_detail.get("IDUMP")
                if condition_id is not None:
                    event.referral.medical_care_condition_id = str(condition_id)
                    event.referral.medical_care_condition_name = str(condition)
                    logger.info(
                        f"Event {event_id}: Установлено условие оказания медпомощи: ID='{condition_id}', Имя='{condition}'")
                else:
                    logger.warning(f"Event {event_id}: В справочнике V006 для '{condition}' отсутствуют данные.")
            else:
                logger.warning(f"Event {event_id}: Запись для '{condition}' в V006 не словарь.")
        else:
            logger.warning(f"Event {event_id}: Условие '{condition}' не найдено в V006 или запись пуста.")

    except AttributeError as e:  # Ловим ошибку, если где-то в цепочке был None там, где не ожидали
        logger.error(
            f"Event {event_id}: Ошибка доступа к данным справочника V006 для условия '{condition}': {e}", exc_info=True)
    except Exception as e:  # Общий обработчик на случай других непредвиденных ошибок
        logger.error(
            f"Event {event_id}: Неожиданная ошибка при получении условия медпомощи для '{condition}': {e}",
            exc_info=True)


async def _get_and_set_referring_organization_details(
        event: Event,
        handbooks_storage: HandbooksStorage,
        raw_referred_data: dict[str, str],
) -> None:
    referral_type_id = str(raw_referred_data.get("PrehospDirect_id", None))
    await _get_and_set_referral_type_name(event, handbooks_storage, referral_type_id)
    event_id = event.service.event_id

    # Инициализируем поля event.referral, чтобы они были None, если ничего не найдено
    event.referral.org_name = None
    event.referral.org_nick = None
    event.referral.org_code = None
    event.referral.org_token = None

    # если направила другая МО
    if referral_type_id == REFERRED_BY_OTHER_MO:
        # справочник направивших на госпитализацию организаций (ЕВМИАС)
        referred_organizations_handbook = get_handbook_payload(
            handbooks_storage, "referred_organizations", event_id
        )
        referred_org_id = raw_referred_data.get("Org_did")
        if isinstance(referred_organizations_handbook, dict) and referred_org_id is not None:
            referred_data = referred_organizations_handbook.get(referred_org_id)

        # справочник МО (от фонда)
        medical_organizations_handbook = get_handbook_payload(
            handbooks_storage, "medical_organizations", event_id
        )
        if isinstance(referred_organizations_handbook, dict):
            handbook_keys = medical_organizations_handbook.keys()

        org_evmias_name = referred_data.get("name")
        org_evmias_token = referred_data.get("token")
        map_keys = referred_org_map.keys()

        if org_evmias_name in map_keys:
            org_map = referred_org_map.get(org_evmias_name)
            event.referral.org_name = org_map.get("name")
            event.referral.org_nick = org_map.get("nick")
            event.referral.org_code = org_map.get("code")[:8]
            event.referral.org_token = org_map.get("token")

        elif (org_evmias_name not in map_keys) and (org_evmias_token in handbook_keys):
            org_handbook = medical_organizations_handbook.get(org_evmias_token)[0]
            event.referral.org_name = org_handbook.get("NAM_MOP")
            event.referral.org_nick = org_handbook.get("NAM_MOK")
            event.referral.org_code = org_handbook.get("IDMO")[:8]
            event.referral.org_token = org_evmias_token

        else:
            logger.warning(
                f"Не удалось найти справочную информацию о направившей организации: "
                f"{org_evmias_name} ({org_evmias_token}).")

    elif referral_type_id == REFERRED_BY_DEPARTMENT:
        # если направило отделение материнской организации
        event.referral.org_name = current_org_map.get("name")
        event.referral.org_nick = current_org_map.get("nick")
        event.referral.org_code = current_org_map.get("tfoms_code")[:8]
        event.referral.org_token = current_org_map.get("tfoms_token")


async def _get_and_set_medical_care_form(
        event: Event,
        handbooks_storage: HandbooksStorage,
        raw_referred_data: dict[str, str]
) -> None:
    """
    Получает форму медпомощи (планово или экстренно)
    и добавляет соответствующий код из справочника фонда V014 к сведениям о направлении на госпитализацию
    """
    event_id = event.service.event_id

    event.referral.medical_care_form_id = None
    event.referral.medical_care_form_name = None

    raw_medical_care_form_id = raw_referred_data.get("PrehospDirect_id")

    if raw_medical_care_form_id is None:
        logger.warning(f"Event {event_id}: PrehospDirect_id отсутствует. Форма медпомощи не будет установлена.")
        return  # Выходим, если нет исходного ID

    medical_care_form_id = str(raw_medical_care_form_id)
    if medical_care_form_id == "2":
        medical_care_form_id = "3"

    event.referral.medical_care_form_id = medical_care_form_id

    medical_care_form_handbook = get_handbook_payload(
        handbooks_storage, "medical_care_forms", event_id
    )

    if isinstance(medical_care_form_handbook, dict):
        handbook_entry = medical_care_form_handbook.get(medical_care_form_id)
        if isinstance(handbook_entry, list) and handbook_entry:
            details = handbook_entry[0]
            if isinstance(details, dict):  # Шаг 4: Проверка, что это словарь
                name = details.get("FRMMPNAME")
                if name is not None:
                    event.referral.medical_care_form_name = str(name)
                    logger.info(
                        f"Event {event_id}: Установлена форма медпомощи: ID='{medical_care_form_id}', Имя='{name}'")
                else:
                    logger.warning(
                        f"Event {event_id}: В V014 для ID '{medical_care_form_id}' отсутствуют данные.")
            else:
                logger.warning(f"Event {event_id}: Запись для ID '{medical_care_form_id}' в V014 не словарь.")
        else:
            logger.warning(
                f"Event {event_id}: ID формы '{medical_care_form_id}' не найден в V014 или запись не список/пуста.")
    else:
        logger.warning(f"Event {event_id}: Справочник V014 ('medical_care_forms') не словарь или не загружен.")


async def _get_raw_movement_data(event_id: str, cookies: dict[str, str], http_service: HTTPXClient) -> dict[str, str]:
    """
    Получает информацию о движении пациента путем запроса к ЕВМИАС
    """
    url = settings.BASE_URL
    headers = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
    params = {"c": "EvnSection", "m": "loadEvnSectionGrid"}
    data = {"EvnSection_pid": event_id}

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
        raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
    )
    json_response = response.get('json')
    if not json_response or not isinstance(json_response, list) or len(json_response) == 0:
        logger.error(f"Event {event_id}: Запрос movement_data пустой или имеет неверный формат.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Некорректный ответ от ЕВМИАС (movement_data) для события {event_id}"
        )
    return json_response[0]


# async def _get_and_set_medical_care_profile(
#         event: Event,
#         handbooks_storage: HandbooksStorage,
#         cookies: dict[str, str],
#         http_service: HTTPXClient
# ) -> None:
#     """
#     Получает профиль медпомощи посредством запроса к ЕВМИАС о движении пациента
#     и добавляет соответствующий код из справочника фонда V002 к сведениям о направлении
#     """
#     event_id = event.service.event_id
#     event.referral.medical_care_profile_id = None
#
#     raw_movement_data = await _get_raw_movement_data(event_id, cookies, http_service)
#     logger.debug(f"Полученные данные о движении пациента: {raw_movement_data}")


async def enrich_event_hospital_referral(
        event: Event,
        handbooks_storage: HandbooksStorage,
        cookies: dict[str, str],
        http_service: HTTPXClient,
) -> Event:
    """ Дополняет сведения о госпитализации сведениями о направлении на госпитализацию"""
    event_id = event.service.event_id
    try:
        await _generate_referral_id_for_xml_unload(event)

        # получаем сведения о направлении на госпитализацию посредством запроса к ЕВМИАС
        raw_referred_data = await _get_raw_referred_data(event_id, cookies, http_service)
        raw_movement_data = await _get_raw_movement_data(event_id, cookies, http_service)

        await _get_and_set_referral_talon_date_and_number(event, raw_referred_data)
        await _get_and_set_referring_organization_details(event, handbooks_storage, raw_referred_data)
        await _get_and_set_medical_care_condition(event, handbooks_storage)
        await _get_and_set_medical_care_form(event, handbooks_storage, raw_referred_data)
        # await _get_and_set_medical_care_profile(event, handbooks_storage, cookies, http_service)

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
