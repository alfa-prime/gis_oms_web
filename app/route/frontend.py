from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any # Импортируем типы

# Предполагаем, что зависимости и клиент настроены как в последнем варианте
from app.core import HTTPXClient, get_http_service, logger
from app.services import set_cookies, fetch_and_filter
# Импортируем модель Pydantic, чтобы создать ее из данных формы
from app.models import PatientSearch

router = APIRouter()
templates = Jinja2Templates(directory="./templates") # Укажи путь к твоей папке templates

# Эндпоинт для отображения формы
@router.get("/", response_class=HTMLResponse)
async def show_search_form(request: Request):
    """Отображает простую HTML форму поиска."""
    context = {}
    return templates.TemplateResponse(request, "search_patient_simple.html", context)


# Эндпоинт для обработки POST-запроса от формы
# @router.post("/find_events", response_class=HTMLResponse)
# async def find_events_from_form(
#     request: Request,
#     # Получаем данные из HTML-формы с помощью Form(...)
#     last_name: str = Form(...),
#     first_name: Optional[str] = Form(None),
#     middle_name: Optional[str] = Form(None),
#     birthday: Optional[str] = Form(None),
#     cookies: dict = Depends(set_cookies),
#     http_service: HTTPXClient = Depends(get_http_service)
# ):
#     """Обрабатывает данные из формы, вызывает API логику и возвращает результат."""
#
#     # 1. Создаем Pydantic модель из данных формы
#     # (Это хороший способ валидировать и структурировать данные)
#     patient_search_data = PatientSearch(
#         last_name=last_name,
#         first_name=first_name or None,
#         middle_name=middle_name or None,
#         birthday=birthday or None
#     )
#
#     results = None
#     error = None
#     try:
#         results = await fetch_and_filter(
#             patient_search_data=patient_search_data,
#             cookies=cookies,
#             http_service=http_service
#         )
#         logger.info(f"Поиск из формы успешен, найдено: {len(results) if results else 0} записей.")
#
#     except HTTPException as e:
#         logger.warning(f"Ошибка при поиске из формы (HTTPException): {e.status_code} - {e.detail}")
#         error = e.detail # Сохраняем сообщение об ошибке для отображения
#     except Exception as e:
#         # Ловим другие возможные ошибки (на всякий случай)
#         logger.error(f"Неожиданная ошибка при поиске из формы: {e}", exc_info=True)
#         error = "Произошла внутренняя ошибка сервера при поиске."
#
#     # 3. Возвращаем тот же шаблон, но с результатами или ошибкой
#     context = {"results": results, "error": error}
#     return templates.TemplateResponse(request, "search_patient_simple.html", context)