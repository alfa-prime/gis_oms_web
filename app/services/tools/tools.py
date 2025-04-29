import json
import zipfile
import aiofiles

from typing import List, Dict
from pathlib import Path as SyncPath
from aiopath import Path as AsyncPath
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logger_setup import logger

settings = get_settings()

HANDBOOKS_DIR = SyncPath(settings.HANDBOOKS_DIR)


async def save_file(file_path: str, content: bytes) -> None:
    """
        Асинхронно сохраняет файл на диск.
        Args:
            file_path (str): Путь, по которому будет сохранён файл.
            content (bytes): Бинарное содержимое для записи.
        Raises:
            OSError: Если запись файла не удалась (например, нет прав или места на диске).
    """
    async with aiofiles.open(file_path, "wb") as file:
        await file.write(content)


async def delete_files(files: List[str]) -> None:
    """Асинхронно удаляет файлы, переданные в списке.
    Args:
        files (List[str]): Список путей к файлам для удаления.
    Raises:
        HTTPException: Если возникла ошибка при удалении файлов.
    """
    try:
        for file in files:
            await AsyncPath(file).unlink()
            logger.info(f"Временный файл {file} удалён.")
    except Exception as e:
        logger.error(f"Ошибка при удалении файлов: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при удалении файлов: {str(e)}"
        )


async def is_zip_file(file_path: str) -> bool:
    """Асинхронно проверяет, является ли файл ZIP-архивом по сигнатуре.

    Args:
        file_path (str): Путь к файлу.
    Returns:
        bool: True, если файл — валидный ZIP, иначе False.
    Raises:
        OSError: Если файл не удалось открыть.
    """
    zip_signature = b"PK\x03\x04"  # Сигнатура ZIP-файла
    async with aiofiles.open(file_path, "rb") as f:
        header = await f.read(4)  # Читаем первые 4 байта
        return header == zip_signature


def extract_zip_safely(zip_path: str, extract_to: SyncPath) -> SyncPath:
    """Безопасно извлекает единственный файл из ZIP."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            logger.debug(f"Список файлов в архиве: {file_list}")
            if len(file_list) == 0:
                raise ValueError(f"Архив {zip_path} пуст")
            if len(file_list) > 1:
                raise ValueError(f"Архив {zip_path} содержит более одного файла: {file_list}")

            member = file_list[0]
            member_path = extract_to / member
            logger.debug(f"Извлекаемый файл: {member}, путь: {member_path}")

            if not member_path.resolve().is_relative_to(extract_to.resolve()):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Небезопасный путь в ZIP-архиве")

            zip_ref.extract(member, extract_to)
            logger.debug(f"Файл извлечён в: {member_path}")
            return member_path
    except zipfile.BadZipFile:
        # Ловим повреждённый или невалидный ZIP и переводим в понятный HTTP-ответ
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Архив повреждён или не является ZIP"
        )


async def save_handbook(data: List[Dict] | dict, filename: str) -> None:
    """Асинхронно сохраняет обработанные данные в JSON-файл."""
    output_path = HANDBOOKS_DIR / filename
    await AsyncPath(HANDBOOKS_DIR).mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
