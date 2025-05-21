from pathlib import Path as SyncPath
from typing import Annotated

from fastapi import APIRouter, Query, Depends, Request, HTTPException, status

from app.core import HTTPXClient, get_settings, get_http_service, HandbooksStorage, logger
from app.services.handbooks.nsi_ffoms import fetch_and_process_handbook
from temp.backup.nsi_ffoms_maps import NSI_HANDBOOKS_MAP

router = APIRouter(prefix="/nsi_foms_handbooks", tags=["Справочники НСИ ФОМС"])

settings = get_settings()
BASE_URL = "https://nsi.ffoms.ru"
HANDBOOKS_DIR = SyncPath(settings.HANDBOOKS_DIR)
TEMP_DIR = SyncPath(settings.TEMP_DIR)


@router.get(
    path="/get_handbook",
    summary="Обновить справочник НСИ ФОМС по коду",
    description="Инициирует загрузку/обновление справочника НСИ ФОМС по его коду. "
                "Данные скачиваются, сохраняются на диск и обновляются в памяти приложения."
)
async def get_or_update_nsi_handbook(
        request: Request,
        code: Annotated[str, Query(..., description="Код справочника НСИ", example="F002")],
        http_service: Annotated[HTTPXClient, Depends(get_http_service)]
):
    """Скачивает/сохраняет справочник НСИ и обновляет его в памяти."""
    try:
        handbooks_storage: HandbooksStorage = request.app.state.handbooks_storage
        details = NSI_HANDBOOKS_MAP[code]
        storage_key = details["handbook_storage_key"]
    except (AttributeError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка конфигурации для кода {code}"
        )

    logger.info(f"Запрос на обновление НСИ '{storage_key}' (код {code})")
    try:
        processed_data = await fetch_and_process_handbook(code, http_service)

        # Если данные успешно получены, обновляем storage
        if processed_data is not None:
            handbooks_storage.handbooks[storage_key] = processed_data
            logger.info(f"НСИ '{storage_key}' обновлен в памяти.")
            return {
                "message": f"Справочник '{storage_key}' (код {code}) обновлен.",
                "data": processed_data
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Не удалось обработать справочник {code}."
            )

    except HTTPException as e:
        raise e
    except Exception as e:  # Ловим другие ошибки
        logger.error(f"Ошибка обновления НСИ {code}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка обновления {code}"
        )
