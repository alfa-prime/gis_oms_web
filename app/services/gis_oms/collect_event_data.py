from fastapi import HTTPException

from app.core import HTTPXClient, logger, get_settings

settings = get_settings()

BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}


async def get_starter_patient_data(
        cookies: dict[str, str], http_service: HTTPXClient, card_number: str
) -> dict[str, str] | None:
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Search", "m": "searchData"}
    data = {"EvnPS_NumCard": card_number, "SearchFormType": "EvnPS"}

    try:
        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
        )
        return response.get('json').get('data')[0]

    except HTTPException as e:
        # Ловим ошибки HTTP, которые могли быть подняты декоратором log_and_catch или самим httpx
        logger.error(f"HTTP ошибка при получении услуг для card_number={card_number}: {e.status_code} - {e.detail}")
        return None
    except Exception as e:
        # Ловим любые другие неожиданные ошибки (ошибки парсинга, сети и т.д.)
        logger.error(f"Неожиданная ошибка при получении услуг для card_number={card_number}: {e}", exc_info=True)
        return None


async def collect_event_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        card_number: str
):
    starter_data = await get_starter_patient_data(cookies, http_service, card_number)
    return starter_data
