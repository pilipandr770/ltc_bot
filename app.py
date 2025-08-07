# app.py - Entry point для Render Web Service
import os
import sys

# Добавляем путь к папке app в sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, 'app')
sys.path.insert(0, app_dir)

# Инициализируем переменную app
app = None

try:
    # Пробуем импортировать web_bot напрямую из папки app
    import web_bot
    app = web_bot.app
    print("Successfully imported web_bot.app")
except ImportError as e:
    print(f"Failed to import web_bot: {e}")
    try:
        # Пробуем как пакет
        from app.web_bot import app as flask_app
        app = flask_app
        print("Successfully imported app.web_bot.app")
    except ImportError as e2:
        print(f"Failed to import app.web_bot: {e2}")
        # Создаем минимальное Flask приложение
        from flask import Flask, jsonify
        app = Flask(__name__)
        
        @app.route('/health')
        def health():
            return jsonify({'status': 'ok', 'message': 'Minimal Flask app running'})
        
        @app.route('/')
        def index():
            return jsonify({'service': 'LTC Trading Bot', 'status': 'minimal mode'})
        
        print("Created minimal Flask app")

# Убеждаемся что app определен
if app is None:
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'emergency', 'message': 'Emergency Flask app'})

if __name__ == '__main__':
    # Для локального запуска
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
