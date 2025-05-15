import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from fastapi import HTTPException, status

from app.core import HTTPXClient, logger, get_settings
from app.models import PatientSearch

settings = get_settings()

# Базовые настройки для запросов
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
KSG_YEAR = settings.KSG_YEAR
SEARCH_PERIOD_START_DATE = settings.SEARCH_PERIOD_START_DATE


async def get_patient_operations(
        cookies: dict[str, str],
        http_service: HTTPXClient,
        event_id: str | None
) -> Optional[List[Dict[str, Any]]]:
    """
    Запрашивает услуги для госпитализации и фильтрует операции.

    Returns:
        - list: Список найденных операций (если есть).
        - []: Пустой список, если услуги найдены, но среди них нет операций.
        - None: Если произошла ошибка при запросе или обработке.
    """
    if not event_id:
        logger.warning("Попытка получить операции без event_id")
        return None

    logger.debug(f"Запрос операций пациента {event_id} начат")
    url = BASE_URL
    headers = HEADERS
    params = {"c": "EvnUsluga", "m": "loadEvnUslugaGrid"}
    data = {"pid": event_id, "parent": "EvnPS"}

    try:
        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
        )

        operations_found = []
        # Безопасно получаем JSON и проверяем, что это список
        event_data = response.get('json')
        if event_data and isinstance(event_data, list):
            for entry in event_data:
                # Проверяем, что элемент списка - словарь и содержит нужный ключ/значение
                if isinstance(entry, dict) and "EvnUslugaOper" in entry.get("EvnClass_SysNick", ""):
                    operations_found.append(entry)
            logger.debug(
                f"Обработка услуг для event_id={event_id} завершена. Найдено операций: {len(operations_found)}")
            # Возвращаем найденные операции (может быть пустым списком)
            return operations_found
        else:
            logger.warning(f"Для event_id={event_id} нет ни одной услуги")
            # logger.warning(f"Ответ для услуг event_id={event_id} не содержит валидный JSON список: {event_data}")
            return None  # Ошибка формата ответа

    except HTTPException as e:
        # Ловим ошибки HTTP, которые могли быть подняты декоратором log_and_catch или самим httpx
        logger.error(f"HTTP ошибка при получении услуг для event_id={event_id}: {e.status_code} - {e.detail}")
        return None
    except Exception as e:
        # Ловим любые другие неожиданные ошибки (ошибки парсинга, сети и т.д.)
        logger.error(f"Неожиданная ошибка при получении услуг для event_id={event_id}: {e}", exc_info=True)
        return None


async def fetch_and_filter(
        patient_search_data: PatientSearch,
        cookies: dict,
        http_service: HTTPXClient
) -> List[Dict[str, Any]]:
    """
        Ищет госпитализации пациента по ФИО/дате рождения и возвращает список данных
        ТОЛЬКО тех госпитализаций, в которых подтверждено наличие операций.
        """
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Search", "m": "searchData"}
    data = {
        "SearchFormType": "EvnPS",
        "Person_Surname": patient_search_data.last_name,
        "PayType_id": 3010101000000048,
        "Okei_id": "100",
        "Date_Type": "1",
        "LpuBuilding_cid": "3010101000000467",
        "EvnSection_disDate_Range": f"{SEARCH_PERIOD_START_DATE} - {datetime.now().strftime('%d.%m.%Y')}",
        "Ksg_Year": KSG_YEAR,
        "SearchType_id": "1",
        # Добавляем опциональные поля, если они не пустые, используя := и **
        **({"Person_Firname": first_name} if (first_name := patient_search_data.first_name) else {}),
        **({"Person_Secname": middle_name} if (middle_name := patient_search_data.middle_name) else {}),
        **({"Person_Birthday": birthday} if (birthday := patient_search_data.birthday) else {}),
    }

    logger.debug(f"Поиск госпитализаций пациента с параметрами: {data}")
    # Выполняем первый запрос (поиск пациента/госпитализаций)
    # Ошибки здесь будут пойманы декоратором @route_handler
    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data
    )

    # Безопасно извлекаем список госпитализаций
    initial_hospitalizations = response.get("json", {}).get("data", [])
    logger.info(f"Найдено {len(initial_hospitalizations)} госпитализаций.")

    # Если первичный поиск ничего не дал
    if not initial_hospitalizations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Госпитализации не найдены."
        )

    # 2. Фильтрация госпитализаций: оставляем только те, где есть операции
    final_hospitalization_list = []
    processed_count = 0
    errors_during_check = 0

    # Последовательно проверяем каждую госпитализацию
    for hosp_entry in initial_hospitalizations:
        event_id = hosp_entry.get("EvnPS_id")
        if not event_id:
            logger.warning(f"Запись госпитализации не содержит EvnPS_id: {hosp_entry}")
            continue  # Пропускаем запись без ID

        processed_count += 1
        # Вызываем функцию проверки операций (она сама обрабатывает свои ошибки и возвращает None при сбое)
        operations_check_result = await get_patient_operations(cookies, http_service, event_id)

        if operations_check_result is None:
            # Ошибка при проверке данной госпитализации
            errors_during_check += 1
            logger.warning(
                f"Не удалось проверить операции для event_id={event_id}, госпитализация исключена из результата.")
        elif operations_check_result:  # True, если список операций НЕ пустой
            # Операции найдены, добавляем данные госпитализации в итоговый список
            final_hospitalization_list.append(hosp_entry)
        # else: operations_check_result == [], операций нет, госпитализацию не добавляем

    # Логируем итоги фильтрации
    logger.info(
        f"Проверено {processed_count} госпитализаций с ID. "
        f"Найдено с операциями: {len(final_hospitalization_list)}. "
        f"Ошибок при проверке операций: {errors_during_check}."
    )

    # Если после фильтрации список пуст
    if not final_hospitalization_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Найдены госпитализации, но ни в одной из них не подтверждено наличие операций (или произошли ошибки при проверке)"
        )

    # 3. Возвращаем отфильтрованный список госпитализаций
    logger.debug(print(json.dumps(final_hospitalization_list, indent=4, ensure_ascii=False)))
    return final_hospitalization_list