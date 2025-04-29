# Этап 1: Сборка зависимостей
# Используем официальный образ Python 3.10 slim как базовый для builder'а
FROM python:3.10 AS builder

# Устанавливаем рабочую директорию для установки зависимостей
WORKDIR /install_dir

# Устанавливаем переменные окружения для pip и Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # Добавляем /install_dir/bin в PATH, чтобы исполняемые файлы зависимостей были доступны
    PATH="/install_dir/bin:${PATH}"

# Копируем только файл зависимостей для использования кэша Docker
COPY ./requirements.txt .

# Устанавливаем зависимости в директорию /install_dir
# Использование --prefix гарантирует, что все установится относительно этой папки
RUN pip install --prefix=/install_dir -r requirements.txt

# Этап 2: Финальный образ приложения
# Используем тот же базовый образ для минимизации размера
FROM python:3.10-slim

# 1) Устанавливаем локали и генерим ru_RU.UTF-8
RUN apt-get update \
 && apt-get install -y --no-install-recommends locales \
 && sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen \
 && locale-gen ru_RU.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# 2) Пробрасываем переменные окружения, чтобы всё в UTF-8
ENV LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    PYTHONIOENCODING=utf-8

# Устанавливаем переменную окружения для пути установки (будет использоваться для PATH)
ENV INSTALL_PATH="/install_dir" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Добавляем bin из папки с установленными зависимостями в PATH
    PATH="${INSTALL_PATH}/bin:${PATH}"

# Системные пакеты, если они НУЖНЫ для работы приложения (а не только для сборки)
# На данный момент для нашего приложения они вроде не требуются.
# Если что-то понадобится (например, для генерации XML или работы с сетью), добавлять сюда.
# RUN apt-get update && apt-get install -y --no-install-recommends some-package \
#     && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию для кода приложения
WORKDIR /code

# Копируем файл зависимостей
COPY ./requirements.txt .

# Устанавливаем зависимости СТАНДАРТНЫМ образом (в /usr/local/lib/...)
# Используем --no-cache-dir для уменьшения размера слоя
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем код приложения ПОСЛЕ установки зависимостей, чтобы лучше использовать кэш
COPY ./app /code/app
COPY ./static /code/static
COPY ./templates /code/templates
# Копируем .env.example на случай, если .env не будет проброшен через docker-compose
# COPY ./.env.example /code/.env

# Указываем порт, который будет слушать uvicorn внутри контейнера
EXPOSE 8000

# Команда по умолчанию для запуска приложения
# Используем 0.0.0.0, чтобы приложение было доступно извне контейнера
# --reload включает автоперезагрузку при изменении кода (удобно для разработки)
# Для production --reload нужно убрать
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]