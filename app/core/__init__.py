from .config import get_settings
from .logger_setup import logger
from .httpx_client import HTTPXClient
from .dependencies import get_redis_client, get_http_service, get_handbooks_storage
from .handbooks import handbooks_storage, load_handbook, HandbooksStorage
from .lifespan_services import (
    init_redis_client,
    shutdown_redis_client,
    init_httpx_client,
    shutdown_httpx_client,
    load_all_handbooks
)


__all__ = [
    "get_settings",
    "logger",
    "HTTPXClient",
    "get_http_service",
    "handbooks_storage",
    "load_handbook",
    "load_all_handbooks",
    "init_httpx_client",
    "shutdown_httpx_client",
    "init_redis_client",
    "shutdown_redis_client",
    "get_redis_client",  # Зависимость для получения клиента Redis
    "HandbooksStorage",
    "get_handbooks_storage"
]
