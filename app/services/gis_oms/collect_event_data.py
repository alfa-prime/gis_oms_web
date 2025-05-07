from app.core import HTTPXClient, logger, HandbooksStorage, get_settings
from app.core.decorators import log_and_catch
from app.models import EventSearch
from app.services import (
    get_polis_id,
    get_starter_patient_data,
    enrich_event_additional_patient_data,
    enrich_event_okato_codes_for_patient_address,
    enrich_insurance_data,
    enrich_event_hospital_referral
)

settings = get_settings()


@log_and_catch(debug=settings.DEBUG_HTTP)
async def collect_event_data_by_card_number(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        handbooks_storage: HandbooksStorage,
        card_number: str
):
    logger.info(f"Начало сбора данных для карты № {card_number}")

    event = await get_starter_patient_data(cookies, http_service, card_number)
    logger.debug(f"Шаг 1/5: Стартовые данные получены (Event ID: {event.hospitalization.id})")

    event = await enrich_event_additional_patient_data(cookies, http_service, event)
    logger.debug(f"Шаг 2/5: Доп. данные пациента и страховки получены")

    event = await get_polis_id(cookies, http_service, event)
    logger.debug(f"Шаг 3/5: ID типа полиса получен ({event.insurance.polis_type_id if event.insurance else 'N/A'})")

    event = await enrich_event_okato_codes_for_patient_address(event, http_service)
    logger.debug(f"Шаг 4/5: Коды ОКАТО получены")

    event = await enrich_insurance_data(event, handbooks_storage, http_service)
    logger.debug(f"Шаг 4/5: Данные страховки получены")



    # TODO: Добавить вызовы для получения операций, диагнозов и т.д. здесь
    # event = await _enrich_event_operations(cookies, http_service, event)
    # logger.debug(f"Шаг 5/X: Список операций получен")
    # ...

    logger.info(f"Сбор данных для карты № {card_number} завершен.")

    return event


@log_and_catch(debug=settings.DEBUG_HTTP)
async def collect_event_data_by_fio_and_card_number(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        handbooks_storage: HandbooksStorage,
        event_search_data: EventSearch
):
    """ Сбор данных о пациенте его госпитализации и операциях по ФИО и номеру карты"""
    logger.info(f"Начало сбора данных для карты № {event_search_data.card_number}")

    event = await get_starter_patient_data(cookies, http_service, event_search_data)
    logger.debug(f"Шаг 1: Стартовые данные получены (Event ID: {event.hospitalization.id})")

    event = await enrich_event_additional_patient_data(cookies, http_service, event)
    logger.debug(f"Шаг 2: Доп. данные пациента и страховки получены")

    event = await get_polis_id(cookies, http_service, event)
    logger.debug(f"Шаг 3: ID типа полиса получен ({event.insurance.polis_type_id if event.insurance else 'N/A'})")

    event = await enrich_event_okato_codes_for_patient_address(event, http_service)
    logger.debug(f"Шаг 4: Коды ОКАТО получены")

    event = await enrich_insurance_data(event, handbooks_storage)
    logger.debug(f"Шаг 5: Данные страховки получены")

    event = await enrich_event_hospital_referral(event, handbooks_storage, cookies, http_service)
    logger.debug(f"Шаг 6: Данные о направлении в больницу получены")

    # TODO: Добавить вызовы для получения операций, диагнозов и т.д. здесь
    # event = await _enrich_event_operations(cookies, http_service, event)
    # logger.debug(f"Шаг X: Список операций получен")
    # ...

    logger.info(f"Сбор данных для карты № {event_search_data.card_number} завершен.")

    return event
