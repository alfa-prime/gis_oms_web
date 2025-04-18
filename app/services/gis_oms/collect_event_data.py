from fastapi import HTTPException, status
from httpx import HTTPStatusError, RequestError

from app.core import HTTPXClient, logger, get_settings
from app.models import Event, InsuranceData
from app.services.fias.fias import get_okato_code

settings = get_settings()

BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}


async def _get_starter_patient_data(
        cookies: dict[str, str], http_service: HTTPXClient, card_number: str
) -> Event:
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


async def _enrich_event_additional_patient_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        event: Event,
):
    person_id = event.service.person_id
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Common", "m": "loadPersonData"}
    data = {
        "Person_id": person_id,
        "LoadShort": True,
        "mode": "PersonInfoPanel"
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

        # Проверяем, что ответ не пустой и содержит данные
        json_response = response.get('json')
        if not json_response or not isinstance(json_response, list) or len(json_response) == 0:
            logger.error(f"Ответ loadPersonData для пациента {person_id} пустой или имеет неверный формат.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Некорректный ответ от ЕВМИАС (loadPersonData) для пациента {person_id}"
            )

        additional_data = json_response[0]

        # --- обогащаем event модель данными из ответа ---
        event.personal.gender_name = additional_data.get('Sex_Name', None)
        # event.service.death_date = additional_data.get('Person_deadDT', None)
        event.personal.death_time = additional_data.get('Person_deadTime', None)
        event.personal.address_registration = additional_data.get('Person_RAddress', None)
        event.personal.address_actual = additional_data.get('Person_PAddress', None)
        event.personal.phone_number = additional_data.get('Person_Phone', None)
        event.personal.snils = additional_data.get('Person_Snils', None)
        event.personal.job_name = additional_data.get('Person_Job', None)
        event.personal.social_status_name = additional_data.get('SocStatus_Name', None)

        event.service.server_pid = additional_data.get('Server_pid', None)
        event.service.sex_id = additional_data.get('Sex_id', None)
        event.service.insurance_company_id = additional_data.get('OrgSmo_id', None)
        event.service.insurance_company_territory_id = additional_data.get('OmsSprTerr_id', None)
        event.service.insurance_company_territory_code = additional_data.get('OmsSprTerr_Code', None)

        event.insurance = InsuranceData.model_validate(additional_data)
        logger.debug(f"Создан и заполнен InsuranceData для event {event.hospitalization.id}")

        logger.info(f"Дополнительные данные для пациента {person_id} успешно получены.")
        return event

    except (HTTPStatusError, RequestError) as e:
        # Эти ошибки уже обработаны в HTTPXClient и/или будут пойманы декоратором @route_handler,
        # который преобразует их в 502, 503, 504 и т.д.
        logger.error(f"Ошибка запроса для пациента {person_id}: {e}")
        raise  # Пробрасываем ошибку, чтобы декоратор ее поймал

    except HTTPException as e:  # Пробрасываем HTTPException, созданную выше при проверке ответа
        raise

    except Exception as e:
        # Ловим остальные ошибки (валидация, парсинг, структура) здесь для логирования
        logger.error(f"Ошибка обработки ответа для пациента {person_id}: {e}", exc_info=True)
        # Пробрасываем дальше, декоратор превратит в 500/400
        raise


async def _get_polis_id(cookies, http_service, event: Event):
    url = BASE_URL
    headers = HEADERS

    params = {"c": "Person", "m": "getPersonEditWindow"}

    data = {
        "person_id": event.service.person_id,
        "server_id": event.service.server_id,
        "attrObjects": "true",
        "mode": [{"object": "PersonEditWindow", "identField": "Person_id"}],
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

        # Проверяем, что ответ не пустой и содержит данные
        json_response = response.get('json')
        if not json_response or not isinstance(json_response, list) or len(json_response) == 0:
            logger.error(f"Ответ на запрос id полиса пустой или имеет неверный формат.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Некорректный ответ от ЕВМИАС на запрос id полиса"
            )

        raw_data = json_response[0]

        # --- обогащаем event модель данными из ответа ---
        event.insurance.polis_type_id = raw_data.get("PolisType_id", None)
        event.service.polis_type_id = raw_data.get("PolisType_id", None)

        return event


    except (HTTPStatusError, RequestError) as e:
        # Эти ошибки уже обработаны в HTTPXClient и/или будут пойманы декоратором @route_handler,
        # который преобразует их в 502, 503, 504 и т.д.
        logger.error(f"Ошибка запроса id полиса: {e}")
        raise  # Пробрасываем ошибку, чтобы декоратор ее поймал

    except HTTPException as e:  # Пробрасываем HTTPException, созданную выше при проверке ответа
        raise

    except Exception as e:
        # Ловим остальные ошибки (валидация, парсинг, структура) здесь для логирования
        logger.error(f"Ошибка обработки ответа для полис id: {e}", exc_info=True)
        # Пробрасываем дальше, декоратор превратит в 500/400
        raise


async def _enrich_event_okato_codes_for_patient_address(event: Event, http_service: HTTPXClient):
    address_registration = event.personal.address_registration
    address_actual = event.personal.address_actual
    address_registration_okato_code = await get_okato_code(address_registration, http_service)
    address_actual_okato_code = await get_okato_code(address_actual, http_service)
    event.personal.address_registration_okato_code = address_registration_okato_code
    event.personal.address_actual_okato_code = address_actual_okato_code
    return event


async def collect_event_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        card_number: str
):
    event = await _get_starter_patient_data(cookies, http_service, card_number)
    event = await _enrich_event_additional_patient_data(cookies, http_service, event)
    event = await _get_polis_id(cookies, http_service, event)
    event = await _enrich_event_okato_codes_for_patient_address(event, http_service)
    return event
