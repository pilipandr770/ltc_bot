FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Копирование файлов требований
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Команда запуска
CMD ["python", "app/bot.py"]
