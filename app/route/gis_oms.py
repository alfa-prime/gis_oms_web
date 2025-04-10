from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Path

from app.core import get_settings, HTTPXClient, get_http_service
from app.core.decorators import route_handler
from app.models import PatientSearch
from app.services import set_cookies, fetch_and_filter, collect_event_data

settings = get_settings()

router = APIRouter(prefix="/evmias-oms", tags=["Сбор данных о пациенте из ЕВМИАС"])


@route_handler(debug=settings.DEBUG_ROUTE)
@router.post("/get_patient")
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


@route_handler(debug=settings.DEBUG_ROUTE)
@router.get(
    path="/get_event/{card_number}",
    summary="Получить детали госпитализации",
    description="Запрашивает детальную информацию о конкретной госпитализации по её ID.",
    responses={  # Документируем возможные ответы
        200: {"description": "Успешный ответ с деталями"},
        404: {"description": "Госпитализация с указанным ID не найдена"},
        500: {"description": "Внутренняя ошибка сервера"},
        502: {"description": "Ошибка при получении данных от внешней системы (ЕВМИАС)"},
    }
)
async def get_event(
        card_number: str = Path(..., description="номер карты пациента"),
        cookies: dict[str, str] = Depends(set_cookies),
        http_service: HTTPXClient = Depends(get_http_service)
):
    """
    Сбор всех данных о госпитализации с id {event_id}
    :param card_number:
    :param cookies:
    :param http_service:
    :return:
    """
    result = await collect_event_data(
        cookies=cookies,
        http_service=http_service,
        card_number=card_number
    )
    return result
