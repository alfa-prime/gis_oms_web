from typing import Annotated, List, Dict, Any

from fastapi import APIRouter, Depends, Path, Body

from app.services import set_cookies
from app.core import HTTPXClient, get_http_service, get_settings

settings = get_settings()
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}

router = APIRouter(prefix="/test", tags=["Тестовые запросы"])

@router.get("/person_data/{person_id}")
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


@router.get("/event_data/{event_id}")
async def smo_name_by_id(
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


@router.get("/fias-token/")
async def get_fias_token(http_service: Annotated[HTTPXClient, Depends(get_http_service)]):
    """
    Получение токена для работы с https://fias-public-service.nalog.ru/api/spas/v2.0/swagger/index.html
    (получение кодов ОКАТО и ОКТМО) GET /api/spas/v2.0/SearchAddressItem
    """
    url = "https://fias.nalog.ru/Home/GetSpasSettings"
    params = {
        "url": "https://fias.nalog.ru/Search?objectId=0&addressType=2&fullName="
    }
    response = await http_service.fetch(
        url=url,
        method="GET",
        params=params,
        raise_for_status=True  # fetch выкинет HTTPStatusError если не 2xx
    )
    return response.get("json", {})