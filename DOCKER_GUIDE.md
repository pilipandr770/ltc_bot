# 🐳 Docker Deployment Guide

## 🎯 Проблема Render решена!

Docker контейнер изолирует приложение и решает проблемы совместимости и таймаутов.

## 🚀 Быстрый деплой на Render с Docker

### 1. Настройка Render:
1. Создайте **Web Service** на render.com
2. Подключите репозиторий: `https://github.com/pilipandr770/ltc_bot.git`
3. Настройки:
   ```
   Environment: Docker
   Dockerfile Path: ./Dockerfile
   ```
4. Environment Variables:
   ```
   BINANCE_API_KEY=your_api_key
   BINANCE_API_SECRET=your_secret_key
   TEST_MODE=false
   ```

### 2. Или используйте render-docker.yaml:
Скопируйте содержимое `render-docker.yaml` в Render Dashboard.

## 🛠️ Локальное тестирование

### 1. Сборка образа:
```bash
cd c:\Users\ПК\bot_binance_ltc_usdt
docker build -t ltc-trading-bot .
```

### 2. Запуск контейнера:
```bash
docker run -d \
  --name ltc-bot \
  --restart unless-stopped \
  -e BINANCE_API_KEY=your_api_key \
  -e BINANCE_API_SECRET=your_secret_key \
  -e TEST_MODE=false \
  -p 5000:5000 \
  ltc-trading-bot
```

### 3. Проверка работы:
```bash
# Логи
docker logs ltc-bot -f

# Health check
curl http://localhost:5000/health

# Статус контейнера
docker ps
```

### 4. Остановка:
```bash
docker stop ltc-bot
docker rm ltc-bot
```

## 🔧 Docker Compose (рекомендуется)

### 1. Создайте .env файл:
```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret_key
```

### 2. Запуск:
```bash
docker-compose up -d
```

### 3. Мониторинг:
```bash
# Логи бота
docker-compose logs ltc-bot -f

# Веб-интерфейс
curl http://localhost:5000/health
```

### 4. Остановка:
```bash
docker-compose down
```

## 📊 Преимущества Docker версии:

✅ **Health Check** - автоматическая проверка работоспособности
✅ **Изоляция** - нет конфликтов зависимостей  
✅ **Restart Policy** - автоматический перезапуск при ошибках
✅ **Портативность** - работает везде одинаково
✅ **Мониторинг** - HTTP endpoint для проверки статуса
✅ **Graceful Shutdown** - корректное завершение

## 🎯 Альтернативные платформы для Docker:

### 1. **Railway** (с Docker):
```bash
railway login
railway init
railway deploy
```

### 2. **Heroku** (с Container Registry):
```bash
heroku container:login
heroku create ltc-bot-docker
heroku container:push worker -a ltc-bot-docker
heroku container:release worker -a ltc-bot-docker
heroku config:set BINANCE_API_KEY=your_key -a ltc-bot-docker
heroku config:set BINANCE_API_SECRET=your_secret -a ltc-bot-docker
```

### 3. **DigitalOcean App Platform**:
Используйте `render-docker.yaml` как основу для конфигурации.

## 🔍 Debugging:

### Локально:
```bash
# Интерактивный режим
docker run -it --rm ltc-trading-bot bash

# Проверка health check
docker exec ltc-bot curl http://localhost:5000/health
```

### На Render:
- Используйте логи в Dashboard
- Health check доступен по URL вашего сервиса

Теперь ваш бот должен работать стабильно! 🎉
