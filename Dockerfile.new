FROM python:3.9-slim

# Установка рабочей директории
WORKDIR /app

# Установка переменных окружения
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY app/ ./app/
COPY *.py ./

# Команда запуска
CMD ["python", "-m", "app.web_bot"]
