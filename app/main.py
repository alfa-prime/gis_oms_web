from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core import (
    logger,
    init_httpx_client,
    shutdown_httpx_client,
    init_redis_client,
    shutdown_redis_client,
    load_all_handbooks
)
from app.route import api_router, web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения: инициализация и закрытие ресурсов.
    """
    # --- Startup Phase ---
    logger.info("Запуск приложения...")
    await init_httpx_client(app)
    await init_redis_client(app)
    await load_all_handbooks()
    logger.info("Инициализация завершена.")

    # --- Приложение работает ---
    yield

    # --- Shutdown Phase ---
    logger.info("Завершение работы приложения...")
    await shutdown_redis_client(app)  # Закрываем Redis перед HTTPX на всякий случай
    await shutdown_httpx_client(app)
    logger.info("Ресурсы освобождены.")


tags_metadata = [
    {"name": "Health check", "description": "Проверка состояния API, HTTP клиента"},
]

app = FastAPI(
    openapi_tags=tags_metadata,
    title="Medical Extractor",
    description="Веб-приложение для сбора данных из ЕВМИАС и генерации XML.",
    lifespan=lifespan
)

# Монтируем статику ДО подключения роутеров
app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключаем маршруты API
app.include_router(api_router)
app.include_router(web_router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/web/")
