import asyncio
from pathlib import Path as SyncPath

import xmltodict
from aiopath import Path as AsyncPath
from fastapi import APIRouter, Query, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from app.core import HTTPXClient, logger, get_settings, get_http_service
from app.services import save_file, is_zip_file, extract_zip_safely, save_handbook, delete_files
from app.services.handbooks.nsi_ffoms import fetch_and_process_handbook

router = APIRouter(prefix="/nsi_foms_handbooks", tags=["Справочники НСИ ФОМС"])

settings = get_settings()
BASE_URL = "https://nsi.ffoms.ru"
HANDBOOKS_DIR = SyncPath(settings.HANDBOOKS_DIR)
TEMP_DIR = SyncPath(settings.TEMP_DIR)


@router.get("/get_handbook", description="Получение справочника НСИ ФОМС по коду")
async def get_nsi_handbook(
        code=Query(..., description="Код справочника", example="F030"),
        http_service: HTTPXClient = Depends(get_http_service)
):
    result = await fetch_and_process_handbook(code, http_service)
    return JSONResponse(
        content=result,
        media_type="application/json; charset=utf-8"
    )



# async def search_registry_by_code(code: str, http_service: HTTPXClient) -> dict:
#     """Поиск справочника по коду"""
#     url = f"{BASE_URL}/data"
#     params = {
#         "pageId": "refbookList",
#         "containerId": "refbookList",
#         "size": "15",
#         "page": "1",
#         "filter.code": code,
#         "sorting.d.code": "ASC",
#     }
#     try:
#         response = await http_service.fetch(url=url, method="GET", params=params)
#         result = response["json"].get("list", [])[0]
#         registry_id, registry_version = result.get("providerParam", "").split("v")
#         result = {"id": registry_id, "version": registry_version, "success": True}
#         logger.info(f"Справочник '{code}' найден.")
#         return result
#     except Exception as e:
#         logger.error(f"Не удалось получить данные по коду. {e}")
#         return {"success": False, "message": f"Не удалось получить данные по коду. {e}"}
#
#
# async def xml_to_dict(file_path: SyncPath) -> dict:
#     """Обработка XML-файла с использованием xmltodict"""
#     try:
#         async with AsyncPath(file_path).open("r", encoding="windows-1251") as f:
#             xml_content = await f.read()
#         parsed_data = xmltodict.parse(xml_content)
#         logger.info(f"XML из файла {file_path} успешно обработан")
#         return {"success": True, "data": parsed_data}
#     except Exception as e:
#         logger.error(f"Ошибка обработки XML: {e}")
#         return {"success": False, "message": f"Ошибка обработки XML: {e}"}
#
#
# @router.get("/get_medical_organization_registry")
# async def get_medical_organization_registry(
#         registry_code=Query(..., description="Код справочника", example="F030"),
#         http_service: HTTPXClient = Depends(get_http_service)
# ):
#     """Получение справочника организаций"""
#     url = f"{BASE_URL}/refbook"
#     saved_file = "medical_organization_registry.zip"
#     output_file = "medical_organization_registry.json"
#     # Получаем параметры справочника
#     handbooks_params = await search_registry_by_code(registry_code, http_service)
#     if not handbooks_params["success"]:
#         logger.error(f"Ошибка при получении параметров справочника: {handbooks_params['message']}")
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=handbooks_params["message"])
#
#     # Формируем параметры запроса для скачивания
#     params = {
#         "type": "XML",
#         "id": handbooks_params["id"],
#         "version": handbooks_params["version"],
#         "searchInput": "ФГБУЗ ММЦ ИМ. Н.И. ПИРОГОВА ФМБА РОССИИ",
#     }
#
#     try:
#         # Выполняем запрос на скачивание файла
#         file_response = await http_service.fetch(url=url, method="GET", params=params)
#         if file_response["status_code"] != 200:
#             logger.error(f"Ошибка при скачивании файла: статус {file_response['status_code']}")
#             raise HTTPException(
#                 status_code=file_response["status_code"],
#                 detail=f"Не удалось скачать файл"
#             )
#
#         # Сохраняем файл асинхронно
#         await save_file(saved_file, file_response["content"])
#         logger.info("Файл успешно сохранён на диск.")
#
#         # Проверяем, что это ZIP-архив
#         is_valid_zip = await is_zip_file(saved_file)
#         if not is_valid_zip:
#             logger.error("Загруженный файл не является ZIP-архивом.")
#             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не является ZIP-архивом.")
#
#         # Распаковываем файл
#         extract_to = TEMP_DIR
#         try:
#             await AsyncPath(extract_to).mkdir(parents=True, exist_ok=True)
#             extracted_file = await asyncio.to_thread(extract_zip_safely, saved_file, extract_to)
#             logger.debug(f"extracted_path: {extracted_file}, type: {type(extracted_file)}")
#             if extracted_file is None:
#                 logger.error("extract_zip_safely вернула None")
#                 raise ValueError("Не удалось извлечь файл из архива")
#             logger.info(f"Файл {saved_file} успешно извлечён в {extracted_file}.")
#         except Exception as e:
#             logger.error(f"Ошибка при распаковке: {str(e)}")
#             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                                 detail=f"Ошибка при распаковке: {str(e)}")
#
#         # Обрабатываем XML
#         processed_data = await xml_to_dict(extracted_file)
#         if not processed_data["success"]:
#             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=processed_data["message"])
#
#         raw_data = processed_data.get("zap", {})
#
#         # Сохраняем справочник
#         await save_handbook(processed_data, output_file)
#         logger.info(f"Справочник сохранён в {HANDBOOKS_DIR}/{output_file}")
#
#         # Удаляем временные файлы
#         await delete_files([extracted_file, saved_file])
#
#         # Возвращаем обработанные данные
#         return {
#             "success": True,
#             "registry_code": registry_code,
#             "version": handbooks_params["version"],
#         }
#
#     except Exception as e:
#         logger.error(f"Ошибка при обработке запроса для '{registry_code}': {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Ошибка при загрузке и обработке файла"
#         )
