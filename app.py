# app.py - Entry point для Render Web Service
import os
import sys

# Добавляем путь к папке app в sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, 'app')
sys.path.insert(0, app_dir)

try:
    # Пробуем импортировать как пакет
    from app.web_bot import app
except ImportError:
    try:
        # Если не получилось, импортируем напрямую
        from web_bot import app
    except ImportError:
        # Если и это не работает, создаем минимальное Flask приложение
        from flask import Flask, jsonify
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({'status': 'ok', 'message': 'Service is running'})
        
        @app.route('/')
        def index():
            return jsonify({'service': 'LTC Trading Bot', 'status': 'minimal mode'})

if __name__ == '__main__':
    # Для локального запуска
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
