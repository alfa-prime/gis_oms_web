import httpx
import redis.asyncio as redis
from fastapi import FastAPI

from app.core import logger, get_settings, load_handbook, handbooks_storage

settings = get_settings()


async def init_httpx_client(app: FastAPI):
    """Инициализирует и сохраняет HTTPX клиент в app.state. При ошибке приложение падает и не стартует."""
    try:
        base_client = httpx.AsyncClient(
            timeout=30.0,
            verify=False,  # Помним про TODO: убрать verify=False
        )
        app.state.http_client = base_client
        logger.info("Базовый HTTPX клиент инициализирован и сохранен в app.state")
    except Exception as e:
        logger.critical(f"КРИТИЧНО: Не удалось инициализировать HTTPX клиент: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize HTTPX client: {e}")


async def shutdown_httpx_client(app: FastAPI):
    """Закрывает HTTPX клиент."""
    if hasattr(app.state, 'http_client') and app.state.http_client:
        try:
            await app.state.http_client.aclose()
            logger.info("Базовый HTTPX клиент закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии HTTPX клиента: {e}", exc_info=True)


async def init_redis_client(app: FastAPI):
    """Инициализирует и сохраняет Redis клиент в app.state. При ошибке приложение падает и не стартует."""
    try:
        redis_pool = redis.ConnectionPool.from_url(
            url=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
            decode_responses=False,
            max_connections=10
        )
        redis_client = redis.Redis(connection_pool=redis_pool)
        await redis_client.ping()  # Проверка соединения
        app.state.redis_client = redis_client
        logger.info(
            f"Redis клиент подключен к {settings.REDIS_HOST}:{settings.REDIS_PORT} (DB {settings.REDIS_DB}) "
            f"и сохранен в app.state"
        )
    except Exception as e:
        logger.critical(f"КРИТИЧНО: Не удалось подключиться к Redis: {e}", exc_info=True)
        raise RuntimeError(f"Failed to connect to Redis: {e}")


async def shutdown_redis_client(app: FastAPI):
    """Закрывает Redis клиент."""
    if hasattr(app.state, 'redis_client') and app.state.redis_client:
        try:
            await app.state.redis_client.close()
            logger.info("Redis клиент закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии Redis клиента: {e}", exc_info=True)


async def load_all_handbooks():
    """Загружает все необходимые справочники."""
    handbooks_storage.handbooks = {}
    # Список имен файлов справочников (без .json)
    handbook_names = [
        "referred_by",
        "referred_lpu_departments",
        "referred_organizations",
        "insurance_companies",
        "rf_subjects"
    ]
    loaded_count = 0
    for name in handbook_names:
        try:
            # Предполагается, что load_handbook находится в app.core.handbooks
            handbooks_storage.handbooks[name] = await load_handbook(name)
            logger.debug(f"Справочник '{name}' загружен.")
            loaded_count += 1
        except FileNotFoundError:
            logger.warning(f"Файл справочника '{name}.json' не найден.")
        except Exception as e:
            logger.warning(f"Не удалось загрузить справочник '{name}': {e}")

    if loaded_count > 0:
        logger.info(
            f"Загружено {loaded_count} из {len(handbook_names)} справочников: {list(handbooks_storage.handbooks.keys())}")
    else:
        logger.warning("Ни один справочник не был загружен.")
