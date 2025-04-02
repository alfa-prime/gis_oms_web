from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import HTTPXClient, logger, load_handbook, handbooks_storage
from app.route import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa
    """
    Управление жизненным циклом приложения:
    - Асинхронная инициализация HTTPXClient и справочников при старте
    - Закрытие HTTPXClient при завершении
    """
    await HTTPXClient.initialize()  # Запускаем клиент
    logger.info("HTTPXClient инициализирован")

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
    await HTTPXClient.shutdown()  # Закрываем клиент при завершении работы
    logger.info("HTTPXClient закрыт")


tags_metadata = [
    {"name": "Health check", "description": "Проверка состояния API, HTTP клиента"},
    {"name": "Collect data from GIS OMS [group]", "description": "Сбор данных из ЕВМИАС для ГИС ОМС"}
]

app = FastAPI(
    openapi_tags=tags_metadata,
    title="Medical Extractor",
    description="Medical Extractor",
    lifespan=lifespan
)

# Подключаем маршруты API
app.include_router(api_router)
