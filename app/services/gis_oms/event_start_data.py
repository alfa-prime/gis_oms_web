from fastapi import HTTPException, status
from httpx import HTTPStatusError, RequestError

from app.core import logger, get_settings, HTTPXClient
from app.models import Event, EventSearch

settings = get_settings()


async def get_starter_patient_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        event_search_data: EventSearch,
) -> Event:
    """
    Выполняет поиск в ЕВМИАС по номеру карты для получения стартовых данных госпитализации.
    Возвращает первый найденный результат.
    Выбрасывает HTTPException при ошибках API, неверном формате ответа или если данные не найдены.
    """
    card_number = event_search_data.card_number
    logger.debug(f"Запрос стартовых данных по номеру карты: {card_number}")
    url = settings.BASE_URL
    headers = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
    params = {"c": "Search", "m": "searchData"}
    data = {
        "EvnPS_NumCard": card_number,
        "SearchFormType": "EvnPS",
        "Person_Surname": event_search_data.last_name,
        # Добавляем опциональные поля, если они не пустые, используя := и **
        **({"Person_Firname": first_name} if (first_name := event_search_data.first_name) else {}),
        **({"Person_Secname": middle_name} if (middle_name := event_search_data.middle_name) else {}),
        **({"Person_Birthday": birthday} if (birthday := event_search_data.birthday) else {}),
    }

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

        json_response = response.get('json')

        if not json_response or 'data' not in json_response:
            logger.error(
                f"Отсутствует ключ 'data' или некорректный JSON для карты {card_number}. "
                f"Ответ: {response.get('text', '')[:500]}"
            )

        if not json_response['data']:
            logger.warning(f"Госпитализация с картой {card_number} не найдена (data: []).")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Госпитализация с номером карты '{card_number}' не найдена."
            )

        data = response.get('json').get('data')[0]
        event = Event.model_validate(data)
        logger.info(f"Стартовые данные для карты {card_number} успешно получены.")
        return event

    except (HTTPStatusError, RequestError) as e:
        # Эти ошибки уже обработаны в HTTPXClient и/или будут пойманы декоратором @route_handler,
        # который преобразует их в 502, 503, 504 и т.д.
        logger.error(f"Ошибка запроса для карты {card_number}: {e}")
        raise  # Пробрасываем ошибку, чтобы декоратор ее поймал

    except Exception as e:
        # Ловим остальные ошибки (валидация, парсинг, структура) здесь для логирования
        logger.error(f"Ошибка обработки ответа для карты {card_number}: {e}", exc_info=True)
        # Пробрасываем дальше, декоратор превратит в 500/400
        raise