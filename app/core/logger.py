import logging
import sys

from loguru import logger
from app.core.config import  get_settings

settings = get_settings()

# Полностью очищаем стандартные хендлеры `logging`
root_logger = logging.getLogger()
root_logger.handlers.clear()

# Очищаем `propagate`, чтобы логи не передавались вверх
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).propagate = False

# Настраиваем `loguru` для логирования FastAPI
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
    level=settings.LOGS_LEVEL,
    colorize=True,
)

logger.add(
    "logs/app.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="INFO",
    rotation="10 MB",  # Разбивка логов на файлы по 10MB
    retention="14 days",  # Храним логи 14 дней
    compression="zip",  # Архивируем старые логи
)

logger.add(
    "logs/errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="ERROR",
    rotation="5 MB",
    retention="10 days",
    compression="zip",
)


# Класс для перехвата логов FastAPI в `loguru`
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Получаем уровень логирования (`INFO`, `ERROR`, и т. д.)
        level = record.levelname if logger.level(record.levelname) is not None else "INFO"

        # Логируем сообщение + исключение (если есть)
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


# Перенаправляем все логи FastAPI в `loguru`
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).handlers = [InterceptHandler()]
