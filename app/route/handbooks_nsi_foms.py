from pathlib import Path as SyncPath

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse

from app.core import HTTPXClient, get_settings, get_http_service
from app.services.handbooks.nsi_ffoms import fetch_and_process_handbook

router = APIRouter(prefix="/nsi_foms_handbooks", tags=["Справочники НСИ ФОМС"])

settings = get_settings()
BASE_URL = "https://nsi.ffoms.ru"
HANDBOOKS_DIR = SyncPath(settings.HANDBOOKS_DIR)
TEMP_DIR = SyncPath(settings.TEMP_DIR)


@router.get("/get_handbook", description="Получение справочника НСИ ФОМС по коду")
async def get_nsi_handbook(
        code=Query(..., description="Код справочника", example="F002"),
        http_service: HTTPXClient = Depends(get_http_service)
):
    result = await fetch_and_process_handbook(code, http_service)
    return JSONResponse(
        content=result,
        media_type="application/json; charset=utf-8"
    )


