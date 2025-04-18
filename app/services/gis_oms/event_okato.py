import asyncio
from typing import Optional

from app.core import HTTPXClient, logger
from app.models import Event, AddressData

from app.services.fias.fias import get_okato_code

async def _fetch_and_update_address_data(
        address_obj: Optional[AddressData],
        http_service: HTTPXClient,
        address_type_log: str  # 'регистрации', 'фактический', 'общий'
) -> Optional[AddressData]:
    """
    Получает данные из ФИАС для одного адреса (если он задан в address_obj)
    и обновляет поля full_address и okato_code этого объекта.

    Возвращает обновленный объект или исходный (может быть None), если адрес невалиден или ФИАС не ответил.
    """
    if not address_obj or not address_obj.address or not address_obj.address.strip():
        logger.debug(f"Адрес {address_type_log} отсутствует или пуст, пропуск запроса к ФИАС.")
        return address_obj  # Возвращаем как есть (может быть None)

    address_str = address_obj.address
    logger.debug(f"Запрос ОКАТО для адреса {address_type_log}: '{address_str[:60]}...'")
    fias_data = await get_okato_code(address_str, http_service)

    if fias_data:
        okato_code = fias_data.get("okato_code")
        full_address = fias_data.get("full_address")
        logger.info(f"ФИАС ОКАТО для адреса {address_type_log}: {okato_code}")
        # Обновляем объект напрямую
        address_obj.full_address = full_address
        address_obj.okato_code = okato_code
    else:
        logger.warning(f"Не удалось получить ОКАТО для адреса {address_type_log}: '{address_str[:60]}...'")
        # Не меняем поля full_address и okato_code, если ФИАС ничего не вернул

    return address_obj


async def enrich_event_okato_codes_for_patient_address(event: Event, http_service: HTTPXClient):
    """
    Добавляет коды ОКАТО и полные адреса из ФИАС в модель Event.
    """
    reg_address_obj = event.personal.registration_address
    actual_address_obj = event.personal.actual_address

    # Извлекаем строки адресов для сравнения
    address_registration_str = reg_address_obj.address if reg_address_obj else None
    address_actual_str = actual_address_obj.address if actual_address_obj else None

    # Проверяем, совпадают ли непустые строки адресов
    are_addresses_valid_and_equal = (
            address_registration_str and address_registration_str.strip() and
            address_actual_str and address_actual_str.strip() and
            address_registration_str.strip() == address_actual_str.strip()
    )

    if are_addresses_valid_and_equal:
        # --- Случай 1: Адреса совпадают и не пустые ---
        logger.info("Адреса совпадают. Один запрос к ФИАС.")
        # Обновляем объект адреса регистрации
        updated_reg_obj = await _fetch_and_update_address_data(
            reg_address_obj,
            http_service,
            address_type_log="общий (регистрации)"
        )

        # Если обновление прошло успешно (ОКАТО получен) и фактический адрес тоже существует (он должен)
        if updated_reg_obj and actual_address_obj and updated_reg_obj.okato_code:
            # Копируем данные в объект фактического адреса
            actual_address_obj.full_address = updated_reg_obj.full_address
            actual_address_obj.okato_code = updated_reg_obj.okato_code
            logger.debug("Данные ОКАТО скопированы для фактического адреса.")
        elif actual_address_obj and not (updated_reg_obj and updated_reg_obj.okato_code):
            # Если ОКАТО не получили для общего адреса
            logger.warning("Не удалось получить ОКАТО для общего адреса, фактический адрес не обновлен.")
            # Оставляем поля фактического адреса как есть (скорее всего None)

    else:
        # --- Случай 2: Адреса разные или один/оба пустые/None ---
        logger.info("Адреса различаются или один из них пуст. Проверяем каждый отдельно.")
        # Запускаем получение данных для обоих адресов параллельно (если они есть)
        tasks = []
        if reg_address_obj:
            tasks.append(_fetch_and_update_address_data(reg_address_obj, http_service, "регистрации"))
        if actual_address_obj:
            tasks.append(_fetch_and_update_address_data(actual_address_obj, http_service, "фактический"))

        if tasks:
            await asyncio.gather(*tasks)  # Выполняем запросы параллельно
            logger.debug("Запросы к ФИАС для разных адресов завершены.")
        else:
            logger.debug("Оба объекта адресов отсутствуют, запросы к ФИАС не выполнялись.")

    return event