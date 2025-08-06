# trading_bot/ltc_bot_minimal.py
import os
import time
import signal
import sys
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

# Глобальная переменная для graceful shutdown
running = True

def signal_handler(signum, frame):
    global running
    log_message("Получен сигнал завершения, останавливаем бота...", "SHUTDOWN")
    running = False

# Регистрируем обработчики сигналов
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def log_message(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    sys.stdout.flush()  # Принудительная очистка буфера для Render

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

def get_klines_minimal(symbol, interval, limit=MA_LONG+5):
    """Получение свечей без numpy - самый простой вариант"""
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception:
        url = 'https://api.binance.com/api/v3/klines'
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        klines = requests.get(url, params=params).json()
    
    # Извлекаем только цены закрытия
    closes = [float(kline[4]) for kline in klines]
    return closes

def calculate_ma_simple(prices, period):
    """Расчет скользящей средней без numpy"""
    if len(prices) < period:
        return None
    
    # Берем последние period цен и считаем среднее
    recent_prices = prices[-period:]
    return sum(recent_prices) / len(recent_prices)

def place_buy_order(symbol, usdt_amount):
    """Покупка LTC за USDT"""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker['price'])
        quantity = round((usdt_amount * TRADE_PERCENTAGE) / price, QUANTITY_PRECISION)
        
        if quantity >= MIN_QUANTITY:
            if not TEST_MODE:
                order = client.order_market_buy(symbol=symbol, quantity=quantity)
                log_message(f"✅ BUY ордер: {quantity} LTC за ~{usdt_amount:.2f} USDT", "ORDER")
                return order
            else:
                log_message(f"🧪 TEST BUY: {quantity} LTC за ~{usdt_amount:.2f} USDT", "TEST")
                return {"status": "TEST"}
        else:
            log_message(f"❌ Занадто мала кількість для покупки: {quantity}", "ERROR")
    except Exception as e:
        log_message(f"❌ Помилка покупки: {e}", "ERROR")
    return None

def place_sell_order(symbol, ltc_amount):
    """Продаж LTC за USDT"""
    try:
        quantity = round(ltc_amount * TRADE_PERCENTAGE, QUANTITY_PRECISION)
        
        if quantity >= MIN_QUANTITY:
            if not TEST_MODE:
                order = client.order_market_sell(symbol=symbol, quantity=quantity)
                log_message(f"✅ SELL ордер: {quantity} LTC", "ORDER")
                return order
            else:
                log_message(f"🧪 TEST SELL: {quantity} LTC", "TEST")
                return {"status": "TEST"}
        else:
            log_message(f"❌ Занадто мала кількість для продажу: {quantity}", "ERROR")
    except Exception as e:
        log_message(f"❌ Помилка продажу: {e}", "ERROR")
    return None

def run_bot():
    global running
    log_message(f"Старт мінімального бота для {SYMBOL} (TEST_MODE: {TEST_MODE})", "STARTUP")
    
    usdt_bal, ltc_bal = get_balances()
    log_message(f"Баланс: {usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC", "BALANCE")
    
    prev_ma7 = prev_ma25 = None
    iteration_count = 0

    while running:
        try:
            # Получаем цены
            prices = get_klines_minimal(SYMBOL, INTERVAL)
            current_price = prices[-1]
            
            # Рассчитываем MA
            curr_ma7 = calculate_ma_simple(prices, MA_SHORT)
            curr_ma25 = calculate_ma_simple(prices, MA_LONG)
            
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
                        if current_usdt >= 1.0:
                            place_buy_order(SYMBOL, current_usdt)
                    
                    # SELL сигнал
                    elif prev_ma7 > prev_ma25 and curr_ma7 < curr_ma25:
                        log_message("📉 Сигнал SELL: MA7 перетнула MA25 вниз", "SIGNAL")
                        if current_ltc >= MIN_QUANTITY:
                            place_sell_order(SYMBOL, current_ltc)

                prev_ma7, prev_ma25 = curr_ma7, curr_ma25
                iteration_count += 1

            # Проверяем running перед сном
            if running:
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log_message("Получен сигнал прерывания", "SHUTDOWN")
            running = False
        except Exception as e:
            log_message(f"Критична помилка: {e}", "ERROR")
            if running:
                time.sleep(CHECK_INTERVAL)
    
    log_message("Бот остановлен", "SHUTDOWN")

if __name__ == '__main__':
    run_bot()
