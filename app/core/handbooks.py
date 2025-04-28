import json
from pathlib import Path
from typing import Any, Dict

import aiofiles

from app.core import logger, get_settings

settings = get_settings()
HANDBOOKS_DIR = Path(settings.HANDBOOKS_DIR)


class HandbooksStorage:
    """ Хранилище справочников, доступные глобально"""
    handbooks: Dict[str, Dict[str, Any]] = {}


handbooks_storage = HandbooksStorage()


async def load_handbook(handbook_name: str) -> Dict[str, Any]:
    """
    Асинхронно загружает указанный справочник из директории HANDBOOKS_DIR.
    Args:
        handbook_name (str): Название справочника (без расширения, например, "referred_by").
    Returns:
        Dict[str, Any]: Загруженный справочник в формате словаря.
    Raises:
        FileNotFoundError: если файл не найден (обработка у вызывающего).
        json.JSONDecodeError: если JSON некорректен (обработка у вызывающего).
    """
    handbook_path = HANDBOOKS_DIR / f"{handbook_name}.json"
    async with aiofiles.open(handbook_path, mode="r", encoding="utf-8") as file:
        content = await file.read()
        handbook = json.loads(content)
    logger.info(f"Handbook {handbook_name} loaded successfully")
    return handbook




