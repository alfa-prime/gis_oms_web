from app.core import HTTPXClient, logger, HandbooksStorage, get_settings
from app.core.decorators import log_and_catch
from app.services import (
    get_polis_id,
    get_starter_patient_data,
    enrich_event_additional_patient_data,
    enrich_event_okato_codes_for_patient_address,
    enrich_insurance_data
)

settings = get_settings()


@log_and_catch(debug=settings.DEBUG_HTTP)
async def collect_event_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        handbooks_storage: HandbooksStorage,
        card_number: str
):
    logger.info(f"Начало сбора данных для карты № {card_number}")

    event = await get_starter_patient_data(cookies, http_service, card_number)
    logger.debug(f"Шаг 1/4: Стартовые данные получены (Event ID: {event.hospitalization.id})")

    event = await enrich_event_additional_patient_data(cookies, http_service, event)
    logger.debug(f"Шаг 2/4: Доп. данные пациента и страховки получены")

    event = await get_polis_id(cookies, http_service, event)
    logger.debug(f"Шаг 3/4: ID типа полиса получен ({event.insurance.polis_type_id if event.insurance else 'N/A'})")

    event = await enrich_event_okato_codes_for_patient_address(event, http_service)
    logger.debug(f"Шаг 4/4: Коды ОКАТО получены")

    event = await enrich_insurance_data(event, handbooks_storage, http_service)

    # TODO: Добавить вызовы для получения операций, диагнозов и т.д. здесь
    # event = await _enrich_event_operations(cookies, http_service, event)
    # logger.debug(f"Шаг 5/X: Список операций получен")
    # ...

    logger.info(f"Сбор данных для карты № {card_number} завершен.")

    return event
