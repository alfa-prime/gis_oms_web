from typing import List, Dict, Any, Annotated

from fastapi import APIRouter, Depends, Path

from app.core import get_settings, HTTPXClient, get_http_service, logger, HandbooksStorage, get_handbooks_storage
from app.core.decorators import route_handler
from app.models import PatientSearch, Event, EventSearch
from app.services import (
    set_cookies,
    fetch_and_filter,
    collect_event_data_by_card_number,
    collect_event_data_by_fio_and_card_number
)

settings = get_settings()

router = APIRouter(prefix="/evmias-oms", tags=["Сбор данных о пациенте из ЕВМИАС"])


@route_handler(debug=settings.DEBUG_ROUTE)
@router.post(
    path="/get_patient",
    summary="Получить список госпитализаций пациента если в них есть операции",
    description="Запрашивает госпитализации пациента по ФИО/дате рождения и возвращает "
                "список госпитализаций, в которых есть операции.",
    responses={  # Документируем возможные ответы
        200: {"description": "Успешный ответ с данными о госпитализациях"},
        404: {"description": "Пациент с указанными данными не найден"},
        500: {"description": "Внутренняя ошибка сервера"},
        502: {"description": "Ошибка при получении данных от внешней системы (ЕВМИАС)"}
    }
)
async def get_patient(
        patient_search: PatientSearch,
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)]
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
@router.post(
    path="/get_event",
    summary="Получение данных о пациенте, его госпитализации и операциях по ФИО и номеру карты",
    description="Запрашивает детальную информацию о пациенте, его госпитализации и операциях по ФИО и номеру карты",
    response_model=Event,
    response_model_by_alias=False,
    responses={  # Документируем возможные ответы
        200: {"description": "Успешный ответ с деталями"},
        404: {"description": "Данные о пациенте с указанными данными не найдены"},
        500: {"description": "Внутренняя ошибка сервера"},
        502: {"description": "Ошибка при получении данных от внешней системы (ЕВМИАС)"},
    }
)
async def get_event_details_by_fio_and_card_number(
        event_search: EventSearch,
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        storage: Annotated[HandbooksStorage, Depends(get_handbooks_storage)],
):
    """
    Сбор стартовых данных о госпитализации по ФИО пациента и номеру карты. (Фамилия и номер карты обязательны)
    """
    logger.info(
        f"Запрос деталей для карты № {event_search.card_number} "
        f"пациента с ФИО {event_search.last_name} {event_search.first_name} {event_search.middle_name}"
    )
    # Вызываем сервис. Он вернет словарь или выбросит исключение.
    # Исключения будут пойманы декоратором @route_handler.
    result = await collect_event_data_by_fio_and_card_number(
        cookies=cookies,
        http_service=http_service,
        handbooks_storage=storage,
        event_search_data=event_search
    )
    return result


@route_handler(debug=settings.DEBUG_ROUTE)
@router.get(
    path="/get_event/{card_number}",
    summary="Получение данных о пациенте, его госпитализации и операциях по номеру карты",
    description="Запрашивает детальную информацию о пациенте, его госпитализации и операциях по номеру карты",
    response_model=Event,
    response_model_by_alias=False,
    responses={
        200: {"description": "Успешный ответ с деталями"},
        404: {"description": "Данные о пациенте с указанными данными не найдены"},
        500: {"description": "Внутренняя ошибка сервера"},
        502: {"description": "Ошибка при получении данных от внешней системы (ЕВМИАС)"},
    }
)
async def get_event_details_by_card(
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)],
        storage: Annotated[HandbooksStorage, Depends(get_handbooks_storage)],
        card_number: str = Path(..., description="номер карты пациента"),
):
    """
    Сбор стартовых данных о госпитализации с номером карты {card_number}.
    """
    logger.info(f"Запрос деталей для карты № {card_number}")
    # Вызываем сервис. Он вернет словарь или выбросит исключение.
    # Исключения будут пойманы декоратором @route_handler.
    result = await collect_event_data_by_card_number(
        cookies=cookies,
        http_service=http_service,
        handbooks_storage=storage,
        card_number=card_number
    )
    return result
