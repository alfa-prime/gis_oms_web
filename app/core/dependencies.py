from typing import TYPE_CHECKING
import redis.asyncio as redis
from fastapi import Request

from app.core import HTTPXClient

# Условный импорт для статического анализа и автодополнения
if TYPE_CHECKING:
    from httpx import AsyncClient

async def get_redis_client(request: Request) -> redis.Redis:
    """
    FastAPI зависимость для получения клиента Redis из app.state.
    Предполагается, что клиент был успешно инициализирован в lifespan.
    """
    return request.app.state.redis_client


async def get_http_service(request: Request) -> HTTPXClient:
    """
    FastAPI зависимость для получения сервиса HTTPXClient из app.state.
    Предполагается, что базовый клиент был успешно инициализирован в lifespan.
    """
    base_client: 'AsyncClient' = request.app.state.http_client
    return HTTPXClient(client=base_client)