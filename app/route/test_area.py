import re
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Body, Query, Request

from app.core import HTTPXClient, get_http_service, get_settings, HandbooksStorage
from app.core.mappings import referred_org_map
from app.services import set_cookies, get_okato_code, get_patient_operations

settings = get_settings()
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
FIAS_API_BASE_URL = settings.FIAS_API_BASE_URL

router = APIRouter(prefix="/test", tags=["Тестовые запросы"])



@router.get(
    path="/test",
)
async def smo_name_by_id(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
):
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Stick", "m": "loadEvnStickGrid"}
    data = {
        "EvnStick_pid": "3010101196271827",
    }

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
    )
    return response.get("json", {})



@router.get(
    path="/person_data/{person_id}",
    summary="Получение базовой информации по id пациента"
)
async def smo_name_by_id(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        person_id: str = Path(..., description="id пациента")
):
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Common", "m": "loadPersonData"}
    data = {
        "Person_id": person_id,
        "LoadShort": True,
        "mode": "PersonInfoPanel"
    }

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
    )
    return response.get("json", {})


@router.get(
    path="/event_data/{event_id}",
    summary="Получение информации по id госпитализации"
)
async def get_event_by_id(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        event_id: str = Path(..., description="id события")
):
    url = BASE_URL
    headers = HEADERS
    params = {"c": "EvnPS", "m": "loadEvnPSEditForm"}
    data = {
        "EvnPS_id": event_id,
        "archiveRecord": "0",
        "delDocsView": "0",
        "attrObjects": [{"object": "EvnPSEditWindow", "identField": "EvnPS_id"}],
    }

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
    )

    return response.get("json", {})


@router.get(path="/fias-token", summary="Получение токена для ФИАС запросов")
async def _get_fias_token(http_service: Annotated[HTTPXClient, Depends(get_http_service)]):
    """
    Получение токена для работы с https://fias-public-service.nalog.ru/api/spas/v2.0/swagger/index.html
    (получение кодов ОКАТО и ОКТМО) GET /api/spas/v2.0/SearchAddressItem
    """
    url = "https://fias.nalog.ru/Home/GetSpasSettings"
    params = {"url": "https://fias.nalog.ru/Search?objectId=0&addressType=2&fullName="}
    response = await http_service.fetch(
        url=url,
        method="GET",
        params=params,
        # raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
    )
    result = response.get("json")["Token"]
    return result


@router.get(path="/fias-okato", summary="Получение кодов ОКАТО для адреса")
async def get_fias_okato(
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        address: str = Query(..., description="Адрес"),
):
    """Получение кода ОКАТО по адресу"""
    result = await get_okato_code(address, http_service)
    return result


@router.get("/period")
async def get_patients_data_for_period(
        request: Request,
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        cookies: dict = Depends(set_cookies),
        start_date: str = Query(
            ...,
            description="Start date in format DD.MM.YYYY",
            regex=r"^\d{2}\.\d{2}\.\d{4}$",
            example="01.01.2025"
        ),
        end_date: str = Query(
            ...,
            description="End date in format DD.MM.YYYY",
            regex=r"^\d{2}\.\d{2}\.\d{4}$",
            example="12.05.2025"
        )):
    """Получаем данные о пациентах за указанный период."""
    url = BASE_URL
    headers = HEADERS
    params = {"c": "Search", "m": "searchData"}

    data = {
        "PersonPeriodicType_id": "1",
        "SearchFormType": "EvnPS",
        "PayType_id": "3010101000000048",  # оплата ОМС
        "Okei_id": "100",
        "Date_Type": "1",
        "LpuBuilding_cid": "3010101000000467",  # стационар ММЦ Пирогова
        "EvnSection_disDate_Range": f"{start_date} - {end_date}",
        "SearchType_id": "1",
        "PersonCardStateType_id": "1",
        "PrivilegeStateType_id": "1",
        "limit": "9999",
    }
    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data
    )

    # Получаем список всех госпитализаций с операциями за указанный период
    raw_hospitalizations = response['json'].get('data', [])
    hospitalizations = {}
    for hosp in raw_hospitalizations:
        event_id = hosp['EvnPS_id']
        operations = await get_patient_operations(cookies, http_service, event_id)

        if operations is not None and len(operations) > 0:
            hospitalizations[event_id] = {
                "person_id:": hosp['Person_id'],
                "operations_count": len(operations),
            }

    # Получаем сведения о направлениях на госпитализацию.
    handbooks_storage: HandbooksStorage = request.app.state.handbooks_storage
    handbook_referred_organizations = handbooks_storage.handbooks.get("referred_organizations", None)
    handbook_medical_organizations = handbooks_storage.handbooks.get("medical_organizations").get("data", None)
    handbook_medical_organizations_params = handbooks_storage.handbooks.get("medical_organizations").get("params", None)

    hosp_outside = {}
    org_names = []
    with_found_code = []
    without_found_code = {
        "params": handbook_medical_organizations_params,
    }

    for event_id, event_data in hospitalizations.items():
        url = BASE_URL
        headers = HEADERS
        params = {"c": "EvnPS", "m": "loadEvnPSEditForm"}
        data = {
            "EvnPS_id": event_id,
            "archiveRecord": "0",
            "delDocsView": "0",
            "attrObjects": [{"object": "EvnPSEditWindow", "identField": "EvnPS_id"}],
        }

        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            headers=headers,
            params=params,
            data=data,
        )

        referral_data = response.get('json')[0]
        referred_by_id = str(referral_data.get("PrehospDirect_id", None))
        referred_org_id = referral_data.get("Org_did")

        referred_data = handbook_referred_organizations.get(referred_org_id, None)
        try:
            org_evmias_name = referred_data.get("name")
            org_evmias_nick = referred_data.get("nick")
            org_evmias_token = referred_data.get("token")
            org_evmias_code = referred_data.get("code")
            org_evmias_f003code = referred_data.get("f003code")
            org_evmias_address = referred_data.get("address")
        except Exception:
            continue

        org_names.append(org_evmias_name)

        if referred_by_id == "2":
            if org_evmias_name in referred_org_map.keys():
                org_map = referred_org_map.get(org_evmias_name)
                event_data.update({
                    "referred_by_id": referred_by_id,
                    "org_name": org_map.get("name"),
                    "org_nick": org_map.get("nick"),
                    "org_code": org_map.get("code"),
                    "org_code_8": org_map.get("code")[0:8],
                    "org_token": org_map.get("token"),
                })
            elif org_evmias_name not in referred_org_map.keys():
                org_handbook = handbook_medical_organizations.get(org_evmias_token)[0]
                event_data.update({
                    "referred_by_id": referred_by_id,
                    "org_name": org_handbook.get("NAM_MOP"),
                    "org_nick": org_handbook.get("NAM_MOK"),
                    "org_code": org_handbook.get("IDMO"),
                    "org_code_8": org_handbook.get("IDMO")[0:8],
                    "org_token": org_evmias_token,

                })

    #         event_data.update({
    #             "referred_by_id": referred_by_id,
    #             "org_evmias_name": org_evmias_name,
    #             "org_evmias_nick": org_evmias_nick,
    #             "org_evmias_token": org_evmias_token,
    #             "org_evmias_code": org_evmias_code,
    #             "org_evmias_f003code": org_evmias_f003code,
    #             "org_evmias_address": org_evmias_address,
    #         })
    #
            hosp_outside[event_id] = event_data
    #
    #         if org_evmias_token is not None and len(org_evmias_token) > 2:
    #             org_handbook = handbook_medical_organizations.get(org_evmias_token)
    #             if org_handbook is not None and org_evmias_name not in with_found_code:
    #                 with_found_code.append(org_evmias_name)
    #         else:
    #             if org_evmias_name not in with_found_code:
    #                 pure_name = org_evmias_name.replace('"', ' ').replace('№', ' ').replace("«", " ").replace("»", " ")
    #                 pure_name = re.sub(r'\s+', ' ', pure_name).strip()
    #
    #                 without_found_code[org_evmias_name] = {
    #                     "org_evmias_name": org_evmias_name,
    #                     "org_pure_name": pure_name,
    #                     "org_evmias_nick": org_evmias_nick,
    #                     "org_evmias_token": org_evmias_token,
    #                     "org_evmias_code": org_evmias_code,
    #                     "org_evmias_f003code": org_evmias_f003code,
    #                     "org_evmias_address": org_evmias_address,
    #                 }
    #
    #     without_found_code.update({"records": len(without_found_code)})
    #
    # org_names = set(org_names)
    # with_found_code = set(with_found_code)
    # # without_found_code = set(without_found_code)

    return {
        # "org_names": {
        #     "records": len(org_names),
        #     "data": org_names,
        # },
        # "with_found_code": {
        #     "records": len(with_found_code),
        #     "data": with_found_code,
        # },
        # "without_found_code": without_found_code,
        "hosp_outside": hosp_outside
    }


@router.post("/person_panel")
async def _get_polis(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        person_id: str = Body(..., description="ID пациента"),
        server_id: str = Body(..., description="ID сервера"),
):
    url = BASE_URL
    headers = HEADERS

    params = {"c": "Person", "m": "getPersonEditWindow"}

    data = {
        "person_id": person_id,
        "server_id": server_id,
        "attrObjects": "true",
        "mode": [{"object": "PersonEditWindow", "identField": "Person_id"}],
    }

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
        raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
    )

    return response.get("json", {})


@router.post("/evn_section_grid")
async def _get_polis(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        event_id: str = Body(..., description="ID госпитализации"),
):
    url = BASE_URL
    headers = HEADERS

    params = {"c": "EvnSection", "m": "loadEvnSectionGrid"}

    data = {
        "EvnSection_pid": event_id,
    }

    response = await http_service.fetch(
        url=url,
        method="POST",
        cookies=cookies,
        headers=headers,
        params=params,
        data=data,
        raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
    )

    return response.get("json", {})
