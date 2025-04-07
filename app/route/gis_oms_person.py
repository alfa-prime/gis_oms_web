from typing import List, Dict, Any

from fastapi import APIRouter, Depends

from app.core import get_settings, HTTPXClient, get_http_service
from app.core.decorators import route_handler
from app.models import PatientSearch
from app.services import set_cookies, fetch_and_filter

settings = get_settings()

router = APIRouter(prefix="/evmias-oms", tags=["Сбор данных о пациенте из ЕВМИАС"])


@router.post("/get_patient")
@route_handler(debug=settings.DEBUG_ROUTE)
async def get_patient(
        patient_search: PatientSearch,
        cookies: dict[str, str] = Depends(set_cookies),
        http_service: HTTPXClient = Depends(get_http_service)
) -> List[Dict[str, Any]]:
    """
    Ищет госпитализации пациента по ФИО/дате рождения и возвращает список данных
    ТОЛЬКО тех госпитализаций, в которых подтверждено наличие операций.
    """
    return await fetch_and_filter(
        patient_search_data=patient_search,
        cookies=cookies,
        http_service=http_service
    )
