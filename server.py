# app.py - Entry point для Render Web Service
import os
import sys

# Добавляем путь к папке app в sys.path для импорта модулей
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, 'app')
sys.path.insert(0, app_dir)

try:
    # Импортируем Flask приложение из web_bot
    from app.web_bot import app
    print("Successfully imported Flask app from app.web_bot")
except ImportError as e:
    print(f"Failed to import app.web_bot: {e}")
    # Fallback - создаем минимальное приложение
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'message': 'Fallback Flask app running'})
    
    @app.route('/')
    def index():
        return jsonify({'service': 'Trading Bot', 'status': 'fallback mode', 'error': str(e)})
    
    print("Created fallback Flask app")

if __name__ == '__main__':
    # Для локального запуска
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
