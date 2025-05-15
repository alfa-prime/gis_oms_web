from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core import logger, HTTPXClient, get_settings, get_http_service, HandbooksStorage
from app.services import set_cookies, save_handbook
from app.services.handbooks.sync_evmias import sync_referred_by, sync_referred_org

settings = get_settings()

# Базовые настройки для запросов
BASE_URL = settings.BASE_URL
HEADERS = {"Origin": settings.BASE_HEADERS_ORIGIN_URL, "Referer": settings.BASE_HEADERS_REFERER_URL}
HANDBOOKS_DIR = settings.HANDBOOKS_DIR

# ID организации (ММЦ Пирогова)
LPU_ID = settings.LPU_ID

router = APIRouter(prefix="/evmias_handbooks", tags=["Справочники ЕВМИАС"])


@router.get(
    path="/referred_by",
    summary="Обновить справочник 'Кем направлен'"
)
async def get_referred_by_handbook(
        request: Request,  # для доступа к app.state
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)]
):
    """
    Инициирует обновление справочника 'Кем направлен' (referred_by).
    Данные скачиваются, сохраняются на диск и обновляются в памяти.
    """

    # Получаем экземпляр HandbooksStorage из app.state
    # Предполагаем, что он был инициализирован в lifespan
    if not hasattr(request.app.state, 'handbooks_storage'):
        logger.error("HandbooksStorage не инициализирован в app.state. Невозможно обновить справочник.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Хранилище справочников не инициализировано."
        )
    handbooks_storage: HandbooksStorage = request.app.state.handbooks_storage

    logger.info("Запрос на обновление справочника 'referred_by' через API.")
    success = await sync_referred_by(
        http_client=http_service,
        cookies=cookies,
        handbooks_storage=handbooks_storage,
        handbook_name="referred_by"
    )

    if success:
        return {
            "message": "Справочник 'referred_by' успешно обновлен.",
            "data": handbooks_storage.handbooks.get("referred_by")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить справочник 'referred_by'."
        )


@router.get(
    path="/referred_organizations",
    summary="Обновить справочник 'Организации, которые направляли пациента'"
)
async def get_referred_organizations_handbook(
        request: Request,  # для доступа к app.state
        cookies: Annotated[dict[str, str], Depends(set_cookies)],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)]
):
    """
    Инициирует обновление справочника 'Организации, которые направляли пациента' (referred_organizations).
    Данные скачиваются, сохраняются на диск и обновляются в памяти.
    """
    if not hasattr(request.app.state, 'handbooks_storage'):
        logger.error("HandbooksStorage не инициализирован в app.state. Невозможно обновить справочник.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Хранилище справочников не инициализировано."
        )
    handbooks_storage: HandbooksStorage = request.app.state.handbooks_storage

    logger.info("Запрос на обновление справочника 'referred_by_org' через API.")
    success = await sync_referred_org(
        http_client=http_service,
        cookies=cookies,
        handbooks_storage=handbooks_storage,
        handbook_name="referred_organizations"
    )

    if success:
        return {
            "message": "Справочник 'referred_organizations' успешно обновлен.",
            "data": handbooks_storage.handbooks.get("referred_organizations")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить справочник 'referred_organizations'."
        )


@router.get("/lpu_departments")
async def get_lpu_departments_handbook(
        cookies: dict = Depends(set_cookies),
        http_service: HTTPXClient = Depends(get_http_service),
):
    """Получаем справочник отделений МО"""
    try:
        logger.debug("Запрос справочника 'lpu_departments' начат")
        url = BASE_URL
        headers = HEADERS
        params = {"c": "Common", "m": "loadLpuSectionList"}
        data = {
            "Lpu_id": LPU_ID,
        }
        response = await http_service.fetch(
            url=url,
            method="POST",
            cookies=cookies,
            params=params,
            data=data,
            headers=headers
        )

        result = {}
        for entry in response['json']:
            result[entry["LpuSection_id"]] = {
                "name": entry["LpuSection_Name"]
            }

        await save_handbook(result, "referred_lpu_departments.json")
        logger.info(f"Справочник 'lpu_departments' сохранен в {HANDBOOKS_DIR}/referred_lpu_departments.json")
        return {"resutl": result}

    except Exception as e:
        logger.error(f"Ошибка в get_lpu_departments_handbook: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения справочника 'lpu_departments': {e}")
