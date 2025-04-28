from app.models import Event
from app.core import logger, HandbooksStorage


async def enrich_insurance_data(
        event: Event,
        handbooks_storage: HandbooksStorage,
) -> Event:
    company_name = event.insurance.company_name
    handbook = handbooks_storage.handbooks.get("insurance_companies", {})
    logger.info(f"Company name: {company_name}")
    logger.info(f"Handbook: {handbook}")
    return event