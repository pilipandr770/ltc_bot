# app_simple.py - Простой entry point без сложных импортов
import os
import sys
import time
import signal
import threading
from datetime import datetime
from flask import Flask, jsonify
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Добавляем путь к папке app
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(current_dir, 'app')
sys.path.insert(0, app_dir)

# Импортируем функции бота
try:
    from bot import run_bot, log_message, get_balances
    bot_available = True
except ImportError as e:
    print(f"Warning: Could not import bot functions: {e}")
    bot_available = False

# Создаем Flask приложение
app = Flask(__name__)

# Глобальные переменные для бота
bot_thread = None
bot_running = False

@app.route('/health')
def health_check():
    """Health check endpoint для Render"""
    try:
        status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'bot_available': bot_available,
            'bot_running': bot_running
        }
        
        if bot_available:
            try:
                usdt_bal, ltc_bal = get_balances()
                status['balance'] = {
                    'usdt': usdt_bal,
                    'ltc': ltc_bal
                }
            except Exception as e:
                status['balance_error'] = str(e)
        
        return jsonify(status), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/')
def index():
    """Главная страница"""
    return jsonify({
        'service': 'LTC Trading Bot',
        'status': 'running',
        'endpoints': ['/health', '/start', '/stop', '/status']
    })

@app.route('/start')
def start_bot():
    """Запуск бота"""
    global bot_thread, bot_running
    
    if not bot_available:
        return jsonify({'error': 'Bot functions not available'}), 500
    
    if bot_running:
        return jsonify({'message': 'Bot already running'})
    
    try:
        bot_running = True
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        return jsonify({'message': 'Bot started successfully'})
    except Exception as e:
        bot_running = False
        return jsonify({'error': f'Failed to start bot: {str(e)}'}), 500

@app.route('/stop')
def stop_bot():
    """Остановка бота"""
    global bot_running
    bot_running = False
    return jsonify({'message': 'Bot stop signal sent'})

@app.route('/status')
def bot_status():
    """Статус бота"""
    try:
        status = {
            'bot_available': bot_available,
            'bot_running': bot_running,
            'timestamp': datetime.now().isoformat()
        }
        
        if bot_available:
            try:
                usdt_bal, ltc_bal = get_balances()
                status['balance'] = {
                    'usdt': round(usdt_bal, 4),
                    'ltc': round(ltc_bal, 6)
                }
            except Exception as e:
                status['balance_error'] = str(e)
        
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    global bot_running
    print("Received shutdown signal, stopping bot...")
    bot_running = False
    sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Автозапуск бота если доступен
    if bot_available:
        try:
            log_message("Starting bot automatically...", "STARTUP")
            bot_running = True
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()
        except Exception as e:
            print(f"Failed to auto-start bot: {e}")
            bot_running = False
    
    # Запускаем Flask приложение
    app.run(host='0.0.0.0', port=port, debug=False)
