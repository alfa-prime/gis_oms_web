from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core import logger, load_handbook, handbooks_storage
# from app.core import HTTPXClient, logger, load_handbook, handbooks_storage
from app.route import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa
    """
    Управление жизненным циклом приложения:
    - Создание и закрытие базового HTTPX клиента.
    - Загрузка справочников.
    """
    # Создаем базовый httpx.AsyncClient
    base_client = httpx.AsyncClient(timeout=30.0, verify=False)
    # Сохраняем его в app.state, чтобы зависимости могли его получить
    app.state.http_client = base_client
    logger.info("Базовый HTTPX клиент инициализирован и сохранен в app.state")

    # await HTTPXClient.initialize()  # Запускаем клиент
    # logger.info("HTTPXClient инициализирован")

    # Загружаем справочники из файлов
    handbooks_storage.handbooks = {}
    handbook_names = [
        "referred_by",
        "referred_lpu_departments",
        "referred_organizations",
        "ensurance_companies",
        "rf_subjects"
    ]
    for name in handbook_names:
        try:
            handbooks_storage.handbooks[name] = await load_handbook(name)
            logger.debug(f"Справочник '{name}' загружен")
        except Exception as e:
            logger.warning(f"Не удалось загрузить справочник '{name}': {e}")

    if any(handbooks_storage.handbooks.values()):
        logger.info(f"Справочники загружены: {list(handbooks_storage.handbooks.keys())}")
    else:
        logger.error("Ни один справочник не загружен")

    yield  # Приложение работает

    # Закрываем базовый клиент при завершении работы
    await app.state.http_client.aclose()
    logger.info("Базовый HTTPX клиент закрыт")
    # await HTTPXClient.shutdown()  # Закрываем клиент при завершении работы
    # logger.info("HTTPXClient закрыт")


tags_metadata = [
    {"name": "Health check", "description": "Проверка состояния API, HTTP клиента"},
]

app = FastAPI(
    openapi_tags=tags_metadata,
    title="Medical Extractor",
    description="Medical Extractor",
    lifespan=lifespan
)

# Монтируем статику ДО подключения роутеров
app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключаем маршруты API
app.include_router(api_router)
