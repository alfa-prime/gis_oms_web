import asyncio
import json

import httpx
import redis.asyncio as redis
from fastapi import FastAPI

from app.core import logger, get_settings, load_handbook, HandbooksStorage, HTTPXClient
from app.services.handbooks.sync_evmias import sync_referred_by
from app.services.cookies.cookies import get_new_cookies, check_existing_cookies, load_cookies_from_redis
from app.services.handbooks.nsi_ffoms_maps import NSI_HANDBOOKS_MAP
from app.services.handbooks.nsi_ffoms import fetch_and_process_handbook

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


async def _get_evmias_cookies_for_lifespan(http_client: HTTPXClient, redis_client: redis.Redis) -> dict | None:
    """Вспомогательная функция для получения cookies ЕВМИАС в lifespan."""
    cookies = await load_cookies_from_redis(redis_client)
    if not cookies or not await check_existing_cookies(redis_client, http_client):
        logger.info("Lifespan: Cookies ЕВМИАС невалидны/отсутствуют, получаем новые для загрузки справочников.")
        cookies = await get_new_cookies(http_client, redis_client)

    if not cookies:
        logger.error("Lifespan: Не удалось получить cookies ЕВМИАС.")
        return None
    logger.info("Lifespan: Cookies ЕВМИАС получены.")
    return cookies


async def load_all_handbooks(app: FastAPI) -> None:
    """
    Инициализирует все справочники при старте:
    1. Пытается загрузить с диска.
    2. Если файла нет или он поврежден, вызывает сервисную функцию для скачивания/обновления.
    """
    if not hasattr(app.state, 'handbooks_storage') or app.state.handbooks_storage is None:
        app.state.handbooks_storage = HandbooksStorage()

    handbooks_storage: HandbooksStorage = app.state.handbooks_storage
    http_client: HTTPXClient = app.state.http_client_service
    redis_client: redis.Redis = app.state.redis_client

    evmias_cookies = None  # Будут получены, если нужны

    # Карта для ЕВМИАС справочников (имя_ключа -> сервисная_функция)
    EVMIAS_SYNC_MAP = {
        "referred_by": sync_referred_by,
        # "lpu_departments": sync_lpu_departments,
    }

    # Список NSI кодов, которые нужно синхронизировать/загрузить при старте
    NSI_CODES_TO_PROCESS = [
        "F002",  # страховые компании
        "V005",  # Классификатор пола
    ]

    # Определяем все ожидаемые ключи в storage (ЕВМИАС + НСИ)
    expected_storage_keys = list(EVMIAS_SYNC_MAP.keys())
    for code in NSI_CODES_TO_PROCESS:
        details = NSI_HANDBOOKS_MAP.get(code)
        if details:
            # Используем storage_key из MAP, если он там есть, иначе генерируем из filename
            storage_key = details.get("handbook_storage_key")
            expected_storage_keys.append(storage_key)
    expected_storage_keys = list(set(expected_storage_keys))

    tasks_to_run_in_parallel = []
    active_sync_tasks_info = []  # Для логирования результатов gather

    # --- Шаг 1: Проверка локальных файлов и планирование задач синхронизации ---
    for key_name in expected_storage_keys:
        needs_sync = False
        try:
            data = await load_handbook(key_name)  # Пытаемся загрузить с диска
            handbooks_storage.handbooks[key_name] = data
            logger.info(f"Справочник '{key_name}' успешно загружен из файла.")
        except FileNotFoundError:
            logger.warning(f"Файл справочника '{key_name}.json' не найден. Требуется синхронизация.")
            needs_sync = True
        except json.JSONDecodeError:
            logger.error(f"Файл справочника '{key_name}.json' поврежден. Требуется синхронизация.")
            needs_sync = True
        except Exception as e:
            logger.error(f"Ошибка при загрузке справочника '{key_name}' из файла: {e}. Требуется синхронизация.",
                         exc_info=True)
            needs_sync = True

        if needs_sync:
            # Ищем, как синхронизировать этот справочник
            if key_name in EVMIAS_SYNC_MAP:
                service_func = EVMIAS_SYNC_MAP[key_name]
                # Откладываем получение cookies до момента, когда они точно нужны
                if evmias_cookies is None and not hasattr(app.state, 'evmias_startup_cookies_fetched'):
                    # ... (логика получения evmias_cookies, как раньше) ...
                    fetched_cookies = await _get_evmias_cookies_for_lifespan(http_client, redis_client)
                    if fetched_cookies:
                        evmias_cookies = fetched_cookies
                        app.state.evmias_startup_cookies_fetched = True
                    else:
                        logger.error("Не удалось получить cookies ЕВМИАС. Пропуск синхронизации ЕВМИАС справочников.")
                        # Устанавливаем флаг, чтобы не пытаться снова
                        app.state.evmias_startup_cookies_fetched = True
                        continue  # Пропускаем добавление этой задачи

                if evmias_cookies:  # Если куки есть (или были получены успешно)
                    logger.info(f"Lifespan: Планирую синхронизацию ЕВМИАС справочника '{key_name}'...")
                    tasks_to_run_in_parallel.append(
                        service_func(http_client=http_client, cookies=evmias_cookies, handbooks_storage=handbooks_storage))
                    active_sync_tasks_info.append({"name": key_name, "type": "evmias"})
                else:
                    logger.warning(f"Пропуск синхронизации ЕВМИАС справочника '{key_name}' из-за отсутствия cookies.")

            else:
                # Ищем соответствующий NSI код по storage_key (key_name)
                found_nsi_code = None
                for code, details in NSI_HANDBOOKS_MAP.items():
                    current_storage_key = details.get("handbook_storage_key")
                    if current_storage_key == key_name and code in NSI_CODES_TO_PROCESS:
                        found_nsi_code = code
                        break

                if found_nsi_code:
                    logger.info(
                        f"Lifespan: Планирую синхронизацию НСИ справочника '{key_name}' (код {found_nsi_code})...")

                    # Напрямую вызываем fetch_and_process_handbook, она сама сохранит и вернет данные
                    # Нам нужно обновить storage, если функция вернула данные
                    # Обернем вызов в корутину, которая обновит storage
                    async def nsi_sync_wrapper(code_to_sync, key_to_update):
                        try:
                            data = await fetch_and_process_handbook(code_to_sync, http_client)
                            if data:
                                handbooks_storage.handbooks[key_to_update] = data
                                return True  # Возвращаем True при успехе
                            else:
                                return False  # Возвращаем False, если данные не получены/обработаны
                        except Exception:
                            # Логирование ошибки произойдет внутри fetch_and_process_handbook или здесь
                            logger.error(f"Исключение в nsi_sync_wrapper для кода {code_to_sync}", exc_info=True)
                            return False  # Возвращаем False при исключении

                    tasks_to_run_in_parallel.append(nsi_sync_wrapper(found_nsi_code, key_name))
                    active_sync_tasks_info.append({"name": key_name, "type": "nsi", "code": found_nsi_code})
                else:
                    logger.warning(
                        f"Для справочника '{key_name}' не найден файл и не найдена соответствующая функция синхронизации. "
                        f"Пропуск синхронизации."
                    )

    # --- Шаг 2: Выполнение всех запланированных задач синхронизации ---
    successful_syncs_count = 0
    if tasks_to_run_in_parallel:
        logger.info(f"Запускаю {len(tasks_to_run_in_parallel)} задач синхронизации справочников...")
        results = await asyncio.gather(*tasks_to_run_in_parallel, return_exceptions=True)

        for i, res in enumerate(results):
            task_info = active_sync_tasks_info[i]
            handbook_name_for_log = task_info["name"]

            if isinstance(res, Exception):
                logger.error(f"Lifespan: Исключение при синхронизации справочника '{handbook_name_for_log}': {res}",
                             exc_info=res)
            elif res is True:
                successful_syncs_count += 1
                logger.info(
                    f"Lifespan: Справочник '{handbook_name_for_log}' "
                    f"успешно синхронизирован (данные обновлены в storage)."
                )
            else:  # res is False (или None, если nsi_sync_wrapper не вернул True)
                logger.error(
                    f"Lifespan: Не удалось синхронизировать справочник '{handbook_name_for_log}' "
                    f"(сервис/wrapper вернул False или None)."
                )

    final_in_memory_count = len(handbooks_storage.handbooks)
    logger.info(
        f"Lifespan: Загрузка/синхронизация справочников завершена. "
        f"Успешно синхронизировано сервисами: {successful_syncs_count}. "
        f"Всего в памяти: {final_in_memory_count} из {len(expected_storage_keys)} ожидаемых."
    )







# async def load_all_handbooks(app: FastAPI) -> None:
#     """
#     Загружает все необходимые справочники и сохраняет их в app.state.
#     """
#     storage = HandbooksStorage()
#
#     handbook_names = [
#         "referred_by",
#         "referred_lpu_departments",
#         "referred_organizations",
#         "insurance_companies",
#         "rf_subjects",
#     ]
#
#     loaded = []
#
#     for name in handbook_names:
#         try:
#             handbook = await load_handbook(name)
#             storage.handbooks[name] = handbook
#             logger.debug(f"Справочник '{name}' успешно загружен.")
#             loaded.append(name)
#         except FileNotFoundError:
#             logger.warning(f"Справочник '{name}.json' не найден.")
#         except Exception as e:
#             logger.warning(f"Ошибка при загрузке справочника '{name}': {e}")
#
#     app.state.handbooks_storage = storage
#
#     if loaded:
#         logger.info(f"Загружено {len(loaded)} справочников: {', '.join(loaded)}")
#     else:
#         logger.warning("Ни один справочник не был загружен.")
