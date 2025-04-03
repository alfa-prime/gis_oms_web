import logging
import sys
from loguru import logger

# Убираем импорт get_settings из глобальной области
def configure_logger(log_level: str = "INFO"):
    """Настраивает loguru для логирования приложения. Вызывается при импорте модуля."""
    # Очистка стандартных хендлеров logging
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).propagate = False

    # Настройка loguru
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
        level=log_level,
        colorize=True,
    )
    logger.add(
        "logs/app.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="14 days",
        compression="zip",
    )
    logger.add(
        "logs/errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="ERROR",
        rotation="5 MB",
        retention="10 days",
        compression="zip",
    )

    # Перехват логов FastAPI
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            level = record.levelname if logger.level(record.levelname) is not None else "INFO"
            logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())

    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).handlers = [InterceptHandler()]

# Вызываем конфигурацию с настройками
from .config import get_settings
settings = get_settings()
configure_logger(settings.LOGS_LEVEL)