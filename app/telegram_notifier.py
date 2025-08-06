# telegram_notifier.py
import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # Добавьте в Render Environment
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')       # Ваш chat ID

def send_telegram_message(message):
    """Отправка уведомления в Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': f"🤖 LTC Bot: {message}",
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=data)
        return response.status_code == 200
    except:
        return False

# Использование в боте:
# send_telegram_message(f"📈 BUY сигнал: {quantity} LTC за {price}")
# send_telegram_message(f"📉 SELL сигнал: {quantity} LTC")
