from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import get_settings, HTTPXClient, logger, get_httpx_client
from app.core.decorators import route_handler
from app.models import PatientSearch
from app.services import set_cookies

settings = get_settings()

# Базовые настройки для запросов
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
KSG_YEAR = settings.KSG_YEAR
SEARCH_PERIOD_START_DATE = settings.SEARCH_PERIOD_START_DATE

router = APIRouter(prefix="/evmias-oms", tags=["Сбор данных о пациенте из ЕВМИАС"])


async def get_patient_operations(
        cookies: dict[str, str],
        httpx_client: HTTPXClient,
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
        response = await httpx_client.fetch(
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
            logger.warning(f"Ответ для услуг event_id={event_id} не содержит валидный JSON список: {event_data}")
            return None  # Ошибка формата ответа

    except HTTPException as e:
        # Ловим ошибки HTTP, которые могли быть подняты декоратором log_and_catch или самим httpx
        logger.error(f"HTTP ошибка при получении услуг для event_id={event_id}: {e.status_code} - {e.detail}")
        return None
    except Exception as e:
        # Ловим любые другие неожиданные ошибки (ошибки парсинга, сети и т.д.)
        logger.error(f"Неожиданная ошибка при получении услуг для event_id={event_id}: {e}", exc_info=True)
        return None
    # result = []
    # event_data = response.get("json")
    # if event_data and isinstance(event_data, list):
    #     for entry in event_data:
    #         if "EvnUslugaOper" not in entry["EvnClass_SysNick"]:
    #             continue
    #         result.append(entry)
    #     return result


@router.post("/get_patient")
@route_handler(debug=settings.DEBUG_ROUTE)
async def get_patient(
        patient_search: PatientSearch,
        cookies: dict[str, str] = Depends(set_cookies),
        httpx_client: HTTPXClient = Depends(get_httpx_client)
)-> List[Dict[str, Any]]:
    """
    Ищет госпитализации пациента по ФИО/дате рождения и возвращает список данных
    ТОЛЬКО тех госпитализаций, в которых подтверждено наличие операций.
    """
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Search", "m": "searchData"}
    data = {
        "SearchFormType": "EvnPS",
        "Person_Surname": patient_search.last_name,
        "PayType_id": "3010101000000048",
        "Okei_id": "100",
        "Date_Type": "1",
        "LpuBuilding_cid": "3010101000000467",
        "EvnSection_disDate_Range": f"{SEARCH_PERIOD_START_DATE} - {datetime.now().strftime('%d.%m.%Y')}",
        "Ksg_Year": KSG_YEAR,
        "SearchType_id": "1",
        # Добавляем опциональные поля, если они не пустые, используя := и **
        **({"Person_Firname": first_name} if (first_name := patient_search.first_name) else {}),
        **({"Person_Secname": middle_name} if (middle_name := patient_search.middle_name) else {}),
        **({"Person_Birthday": birthday} if (birthday := patient_search.birthday) else {}),
    }

    # if patient_search.first_name:
    #     data["Person_Firname"] = patient_search.first_name
    # if patient_search.middle_name:
    #     data["Person_Secname"] = patient_search.middle_name
    # if patient_search.birthday:
    #     data["Person_Birthday"] = patient_search.birthday

    logger.debug(f"Поиск госпитализаций пациента с параметрами: {data}")
    # Выполняем первый запрос (поиск пациента/госпитализаций)
    # Ошибки здесь будут пойманы декоратором @route_handler
    response = await httpx_client.fetch(
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
        operations_check_result = await get_patient_operations(cookies, httpx_client, event_id)

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
    return final_hospitalization_list

    # data_raw = response["json"].get("data", [])
    #
    # result = dict()
    #
    # for entry in data_raw:
    #     event_id = entry.get("EvnPS_id", "")
    #     event_data = await get_patient_operations(cookies, httpx_client, event_id)
    #     result[event_id] = {
    #         "data": entry,
    #         "operations": event_data,
    #     }
    #
    # if not result:
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND,
    #         detail="Пациент не найден"
    #     )
    # return result
