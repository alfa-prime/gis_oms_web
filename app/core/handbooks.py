import aiofiles
import json
from pathlib import Path
from typing import Any, Dict

from app.core.logger import logger
from app.core.config import get_settings

settings = get_settings()
HANDBOOKS_DIR = settings.HANDBOOKS_DIR


class HandbooksStorage:
    """ Хранилище справочников, доступные глобально"""
    handbooks: Dict[str, Dict[str,Any]] = {}

handbooks_storage = HandbooksStorage()


async def load_handbook(handbook_name: str) -> Dict[str, Any]:
    """
    Асинхронно загружает указанный справочник из директории HANDBOOKS_DIR.
    Args:
        handbook_name (str): Название справочника (без расширения, например, "referred_by").
    Returns:
        Dict[str, Any]: Загруженный справочник в формате словаря.
    Raises:
        FileNotFoundError: Если файл справочника не найден.
        json.JSONDecodeError: Если файл содержит некорректный JSON.
    """
    handbook_path = str(Path(HANDBOOKS_DIR) / f"{handbook_name}.json")
    try:
        async with aiofiles.open(handbook_path, mode="r", encoding="utf-8") as file:
            content = await file.read()
            handbook = json.loads(content)
        logger.info (f"Handbook {handbook_name} loaded successfully")
        return handbook
    except FileNotFoundError:
        logger.error(f"Handbook {handbook_name} not found")
        raise
    except json.JSONDecodeError:
        logger.error(f"Error decoding handbook {handbook_name}")
        raise