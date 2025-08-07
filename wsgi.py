# wsgi.py - WSGI entry point для gunicorn
import os
import sys

# Добавляем текущую директорию и папку app в Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'app'))

try:
    # Пробуем импортировать web_bot из папки app
    from web_bot import app
    print("✅ Successfully imported Flask app from web_bot")
except Exception as e:
    print(f"❌ Failed to import web_bot: {e}")
    # Создаем минимальное приложение
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'message': 'Backup Flask app running'})
    
    @app.route('/')
    def index():
        return jsonify({'service': 'LTC Trading Bot Backup', 'version': '1.0'})
    
    print("✅ Created backup Flask app")

# Убеждаемся что переменная app экспортируется
application = app

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
