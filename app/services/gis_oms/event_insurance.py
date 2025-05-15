from app.core import HandbooksStorage, get_settings
from app.core.decorators import log_and_catch
from app.models import Event

settings = get_settings()


@log_and_catch(debug=settings.DEBUG_HTTP)
async def enrich_insurance_data(
        event: Event,
        handbooks_storage: HandbooksStorage,
) -> Event:
    company_name = event.insurance.company_name
    handbook = handbooks_storage.handbooks.get("insurance_companies", None)
    handbook_data = handbook.get('data')
    company_data = handbook_data.get(company_name, {})[0]
    event.insurance.territory_code = company_data.get('TF_OKATO', '')
    event.insurance.code = company_data.get('smocod', '')
    return event
