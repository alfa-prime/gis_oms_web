import json

from fastapi import HTTPException

from app.core import HTTPXClient, logger, get_settings
from app.models import Event

settings = get_settings()

BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}


async def get_starter_patient_data(
        cookies: dict[str, str], http_service: HTTPXClient, card_number: str
) -> Event | None:
    """
    Выполняет поиск в ЕВМИАС по номеру карты для получения стартовых данных госпитализации.
    Возвращает первый найденный результат.
    Выбрасывает HTTPException при ошибках API, неверном формате ответа или если данные не найдены.
    """
    logger.debug(f"Запрос стартовых данных по номеру карты: {card_number}")
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
            raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
        )
        data = response.get('json').get('data')[0]
        event = Event.model_validate(data)
        return event

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
    event = await get_starter_patient_data(cookies, http_service, card_number)
    return event
