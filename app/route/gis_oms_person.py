from datetime import datetime

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


async def get_patient_operations(cookies: dict[str, str], event_id: str):
    """Запрашиваем операции пациента по id госпитализации"""
    logger.debug(f"Запрос операций пациента {event_id} начат")
    url = BASE_URL
    headers = HEADERS
    params = {"c": "EvnUsluga", "m": "loadEvnUslugaGrid"}
    data = {
        "pid": event_id,
        "parent": "EvnPS",
    }
    response = await HTTPXClient.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
    )

    result = []
    event_data = response['json']
    for entry in event_data:
        if "EvnUslugaOper" not in entry["EvnClass_SysNick"]:
            continue
        result.append(entry)
    return result


@router.post("/get_patient")
@route_handler(debug=settings.DEBUG_ROUTE)
async def get_patient(
        patient_search: PatientSearch,
        cookies: dict[str, str] = Depends(set_cookies),
        httpx_client: HTTPXClient = Depends(get_httpx_client)
):
    # запрашиваем первоначальные данные пациента по данным из веб=формы
    # try:
    url = BASE_URL
    headers = HEADERS
    # params = {"c": "", "m": ""}
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
    }

    if patient_search.first_name:
        data["Person_Firname"] = patient_search.first_name
    if patient_search.middle_name:
        data["Person_Secname"] = patient_search.middle_name
    if patient_search.birthday:
        data["Person_Birthday"] = patient_search.birthday

    response = await httpx_client.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data
    )

    data_raw = response["json"].get("data", [])

    result = dict()

    for entry in data_raw:
        event_id = entry.get("EvnPS_id", "")
        event_data = await get_patient_operations(cookies, event_id)
        result[event_id] = {
            "data": entry,
            "operations": event_data,
        }

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент не найден"
        )
    return result
