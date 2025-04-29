from fastapi import status, HTTPException
from httpx import HTTPStatusError, RequestError

from app.core import logger, get_settings, HTTPXClient
from app.models import Event, AddressData, InsuranceData

settings = get_settings()


async def enrich_event_additional_patient_data(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        event: Event,
):
    person_id = event.service.person_id

    url = settings.BASE_URL
    headers = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
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
        event.personal.gender_id = additional_data.get('Sex_id', None)
        event.personal.gender_name = additional_data.get('Sex_Name', None)
        event.personal.phone_number = additional_data.get('Person_Phone', None)
        event.personal.snils = additional_data.get('Person_Snils', None)
        event.personal.job_name = additional_data.get('Person_Job', None)
        event.personal.social_status_name = additional_data.get('SocStatus_Name', None)

        reg_addr_str = additional_data.get('Person_RAddress')
        if reg_addr_str:
            # Создаем или обновляем объект AddressData для адреса регистрации
            if event.personal.registration_address is None:
                event.personal.registration_address = AddressData(address=reg_addr_str)
            else:
                event.personal.registration_address.address = reg_addr_str
            logger.debug(f"Установлен адрес регистрации: '{reg_addr_str[:60]}...'")
        else:
            logger.debug("Адрес регистрации отсутствует в ответе loadPersonData.")
            event.personal.registration_address = None  # Убедимся, что он None, если строка пустая

        actual_addr_str = additional_data.get('Person_PAddress')
        if actual_addr_str:
            # Создаем или обновляем объект AddressData для фактического адреса
            if event.personal.actual_address is None:
                event.personal.actual_address = AddressData(address=actual_addr_str)
            else:
                event.personal.actual_address.address = actual_addr_str
            logger.debug(f"Установлен фактический адрес: '{actual_addr_str[:60]}...'")
        else:
            logger.debug("Фактический адрес отсутствует в ответе loadPersonData.")
            event.personal.actual_address = None  # Убедимся, что он None

        event.service.server_pid = additional_data.get('Server_pid', None)

        # Если данные о страховой компании и ее территории существуют, создаем объект и заполняем его данными
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
