# trading_bot/ltc_bot_simple.py
import os
import time
import numpy as np
from datetime import datetime
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv
import requests

# Завантаження ключів з файлу .env
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
if not API_KEY or not API_SECRET:
    print("❌ ОШИБКА: Відсутні API ключі Binance! Перевірте файл .env.")
    exit(1)

# Налаштування бота
SYMBOL = 'LTCUSDT'
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
MA_SHORT = 7
MA_LONG = 25
CHECK_INTERVAL = 20
TRADE_PERCENTAGE = 0.95
TEST_MODE = False

def log_message(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")

# Підключення до Binance з автокорекцією часу
try:
    client = Client(API_KEY, API_SECRET)
    server_time = client.get_server_time()
    local_time = int(time.time() * 1000)
    time_offset = server_time['serverTime'] - local_time
    
    if abs(time_offset) > 500:
        client.timestamp_offset = time_offset - 1000
        log_message(f"Застосовано корекцію часу: {time_offset}ms", "TIME")
    
    client.ping()
    log_message("Підключення до Binance успішне", "SUCCESS")
except Exception as e:
    log_message(f"Помилка підключення до Binance: {e}", "ERROR")
    exit(1)

def get_symbol_info(symbol):
    info = client.get_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            prec = 6
            min_qty = 0.0001
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step = float(f['stepSize'])
                    min_qty = float(f['minQty'])
                    prec = len(str(step).split('.')[-1].rstrip('0'))
            return prec, min_qty
    return 6, 0.0001

QUANTITY_PRECISION, MIN_QUANTITY = get_symbol_info(SYMBOL)

def get_balances():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            usdt_balance = float(client.get_asset_balance('USDT')['free'])
            ltc_balance = float(client.get_asset_balance('LTC')['free'])
            return usdt_balance, ltc_balance
        except Exception as e:
            if "1021" in str(e) and attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                log_message(f"Помилка отримання балансу: {e}", "ERROR")
                return 0.0, 0.0

def get_klines_simple(symbol, interval, limit=MA_LONG+5):
    """Получение свечей без pandas"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception:
        url = 'https://api.binance.com/api/v3/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        klines = requests.get(url, params=params).json()
    
    # Извлекаем цены закрытия
    closes = [float(kline[4]) for kline in klines]
    return np.array(closes)

def calculate_ma(prices, period):
    """Расчет скользящей средней с numpy"""
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def run_bot():
    log_message(f"Старт бота для {SYMBOL} (TEST_MODE: {TEST_MODE})", "STARTUP")
    
    usdt_bal, ltc_bal = get_balances()
    log_message(f"Баланс: {usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC", "BALANCE")
    
    prev_ma7 = prev_ma25 = None
    iteration_count = 0

    while True:
        try:
            # Получаем цены
            prices = get_klines_simple(SYMBOL, INTERVAL)
            current_price = prices[-1]
            
            # Рассчитываем MA
            curr_ma7 = calculate_ma(prices, MA_SHORT)
            curr_ma25 = calculate_ma(prices, MA_LONG)
            
            if curr_ma7 is not None and curr_ma25 is not None:
                if iteration_count % 10 == 0:
                    usdt_bal, ltc_bal = get_balances()
                    log_message(f"Баланс: {usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC", "BALANCE")
                
                current_usdt, current_ltc = get_balances()
                current_asset = "LTC" if current_ltc >= MIN_QUANTITY else "USDT"
                ma_direction = "MA7>MA25" if curr_ma7 > curr_ma25 else "MA7<MA25"
                should_have = "LTC" if curr_ma7 > curr_ma25 else "USDT"
                status_emoji = "✅" if current_asset == should_have else "⚠️"
                
                log_message(f"Ціна: {current_price:.4f} | MA7={curr_ma7:.4f}, MA25={curr_ma25:.4f} | {ma_direction} | Актив: {current_asset} {status_emoji}", "MA")
                
                if prev_ma7 is not None:
                    # BUY сигнал
                    if prev_ma7 < prev_ma25 and curr_ma7 > curr_ma25:
                        log_message("📈 Сигнал BUY: MA7 перетнула MA25 вгору", "SIGNAL")
                        if not TEST_MODE and current_usdt >= 1.0:
                            # Здесь можно добавить логику покупки
                            log_message("💰 Покупка LTC", "ORDER")
                    
                    # SELL сигнал
                    elif prev_ma7 > prev_ma25 and curr_ma7 < curr_ma25:
                        log_message("📉 Сигнал SELL: MA7 перетнула MA25 вниз", "SIGNAL")
                        if not TEST_MODE and current_ltc >= MIN_QUANTITY:
                            # Здесь можно добавить логику продажи
                            log_message("💰 Продаж LTC", "ORDER")

                prev_ma7, prev_ma25 = curr_ma7, curr_ma25
                iteration_count += 1

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log_message(f"Критична помилка: {e}", "ERROR")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    run_bot()
