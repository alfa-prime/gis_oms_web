from app.models import Event
from app.core import logger, HandbooksStorage, HTTPXClient, get_settings
from app.services.handbooks.nsi_ffoms import fetch_and_process_handbook
from app.core.decorators import log_and_catch


settings = get_settings()

@log_and_catch(debug=settings.DEBUG_HTTP)
async def enrich_insurance_data(
        event: Event,
        handbooks_storage: HandbooksStorage,
        http_service: HTTPXClient

) -> Event:
    company_name = event.insurance.company_name
    handbook = handbooks_storage.handbooks.get("insurance_companies", None)

    if handbook is None:
        logger.info("Справочник 'insurance_companies' не найден. Пытаюсь загрузить...")
        code = 'F002'
        handbook = await fetch_and_process_handbook(code, http_service)
        handbooks_storage.handbooks["insurance_companies"] = handbook
        logger.info("Справочник 'insurance_companies' загружен и добавлен в память.")

    company_data = handbook.get(company_name, {})[0]

    event.insurance.territory_code = company_data.get('TF_OKATO', '')
    event.insurance.code = company_data.get('smocod', '')

    logger.info(f"Company name: {company_name}")
    logger.info(f"Company data: {company_data}")
    return event