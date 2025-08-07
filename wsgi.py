# wsgi.py - WSGI entry point для gunicorn
import os
import sys

print("🚀 WSGI starting...")
print(f"Current working directory: {os.getcwd()}")
print(f"Python path: {sys.path[:3]}...")

# Добавляем текущую директорию и папку app в Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, 'app')
sys.path.insert(0, current_dir)
sys.path.insert(0, app_dir)

print(f"Added to path: {current_dir}, {app_dir}")
print(f"Files in current dir: {os.listdir(current_dir)[:10]}")
print(f"Files in app dir: {os.listdir(app_dir)[:10]}")

try:
    # Пробуем импортировать web_bot из папки app
    print("Attempting to import web_bot...")
    from web_bot import app
    print("✅ Successfully imported Flask app from web_bot")
    print(f"App type: {type(app)}")
except Exception as e:
    print(f"❌ Failed to import web_bot: {e}")
    print(f"Exception type: {type(e)}")
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
print(f"Final app object: {type(app)}")
print("🎯 WSGI ready!")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
