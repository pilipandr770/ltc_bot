# web_bot.py - Версия для деплоя как Web Service
import os
import time
import signal
import sys
import threading
from datetime import datetime
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv
import requests
from flask import Flask, jsonify

# Завантаження ключів з файлу .env
load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

app = Flask(__name__)

# Налаштування бота
SYMBOL = 'LTCUSDT'
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
MA_SHORT = 7
MA_LONG = 25
CHECK_INTERVAL = 20
TRADE_PERCENTAGE = 0.95
TEST_MODE = False

# Глобальные переменные
running = True
bot_thread = None
bot_status = {"status": "starting", "last_update": None, "balance": None}

def log_message(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    sys.stdout.flush()

# Подключение к Binance
if API_KEY and API_SECRET:
    try:
        client = Client(API_KEY, API_SECRET)
        server_time = client.get_server_time()
        local_time = int(time.time() * 1000)
        time_offset = server_time['serverTime'] - local_time
        
        if abs(time_offset) > 500:
            client.timestamp_offset = time_offset - 1000
            log_message(f"Корекція часу: {time_offset}ms", "TIME")
        
        client.ping()
        log_message("Підключення до Binance успішне", "SUCCESS")
        bot_status["status"] = "connected"
    except Exception as e:
        log_message(f"Помилка підключення: {e}", "ERROR")
        client = None
        bot_status["status"] = "error"
else:
    client = None
    bot_status["status"] = "no_api_keys"

def get_symbol_info(symbol):
    if not client:
        return 6, 0.0001
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

# Минимальная стоимость сделки для Binance (обычно 10 USDT)
MIN_NOTIONAL = 10.0

# Минимальная сумма для определения основного актива (5 USDT)  
MIN_ASSET_VALUE = 5.0

def get_balances():
    if not client:
        return 0.0, 0.0
    try:
        usdt_balance = float(client.get_asset_balance('USDT')['free'])
        ltc_balance = float(client.get_asset_balance('LTC')['free'])
        return usdt_balance, ltc_balance
    except Exception as e:
        log_message(f"Помилка балансу: {e}", "ERROR")
        return 0.0, 0.0

def get_klines_minimal(symbol, interval, limit=MA_LONG+5):
    if not client:
        return [119.0] * limit  # Фиктивные данные
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        closes = [float(kline[4]) for kline in klines]
        return closes
    except Exception:
        return [119.0] * limit

def calculate_ma_simple(prices, period):
    if len(prices) < period:
        return None
    recent_prices = prices[-period:]
    return sum(recent_prices) / len(recent_prices)

def place_buy_order(symbol, usdt_amount):
    if not client:
        log_message("🧪 TEST BUY (no API)", "TEST")
        return {"status": "TEST"}
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker['price'])
        quantity = round((usdt_amount * TRADE_PERCENTAGE) / price, QUANTITY_PRECISION)
        notional_value = usdt_amount * TRADE_PERCENTAGE
        
        log_message(f"Попытка покупки: {quantity:.6f} LTC за {price:.4f} USDT = {notional_value:.2f} USDT", "INFO")
        
        if quantity >= MIN_QUANTITY and notional_value >= MIN_NOTIONAL:
            if not TEST_MODE:
                order = client.order_market_buy(symbol=symbol, quantity=quantity)
                log_message(f"✅ BUY: {quantity:.6f} LTC за {notional_value:.2f} USDT", "ORDER")
                return order
            else:
                log_message(f"🧪 TEST BUY: {quantity:.6f} LTC за {notional_value:.2f} USDT", "TEST")
                return {"status": "TEST"}
        elif quantity < MIN_QUANTITY:
            log_message(f"❌ Слишком мало LTC для покупки: {quantity:.6f} < {MIN_QUANTITY}", "WARNING")
        else:
            log_message(f"❌ Слишком малая сумма сделки: {notional_value:.2f} < {MIN_NOTIONAL} USDT", "WARNING")
    except Exception as e:
        log_message(f"❌ Помилка покупки: {e}", "ERROR")
    return None

def place_sell_order(symbol, ltc_amount):
    if not client:
        log_message("🧪 TEST SELL (no API)", "TEST")
        return {"status": "TEST"}
    try:
        quantity = round(ltc_amount * TRADE_PERCENTAGE, QUANTITY_PRECISION)
        # Получаем текущую цену для расчета notional value
        current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        notional_value = quantity * current_price
        
        log_message(f"Попытка продажи: {quantity:.6f} LTC за {current_price:.4f} USDT = {notional_value:.2f} USDT", "INFO")
        
        if quantity >= MIN_QUANTITY and notional_value >= MIN_NOTIONAL:
            if not TEST_MODE:
                order = client.order_market_sell(symbol=symbol, quantity=quantity)
                log_message(f"✅ SELL: {quantity:.6f} LTC за {notional_value:.2f} USDT", "ORDER")
                return order
            else:
                log_message(f"🧪 TEST SELL: {quantity:.6f} LTC за {notional_value:.2f} USDT", "TEST")
                return {"status": "TEST"}
        elif quantity < MIN_QUANTITY:
            log_message(f"❌ Слишком мало LTC для продажи: {quantity:.6f} < {MIN_QUANTITY}", "WARNING")
        else:
            log_message(f"❌ Слишком малая сумма сделки: {notional_value:.2f} < {MIN_NOTIONAL} USDT", "WARNING")
    except Exception as e:
        log_message(f"❌ Помилка продажу: {e}", "ERROR")
    return None
    return None

def trading_bot():
    global running, bot_status
    
    log_message(f"Старт веб-бота для {SYMBOL}", "STARTUP")
    prev_ma7 = prev_ma25 = None
    iteration_count = 0

    while running:
        try:
            prices = get_klines_minimal(SYMBOL, INTERVAL)
            current_price = prices[-1]
            
            curr_ma7 = calculate_ma_simple(prices, MA_SHORT)
            curr_ma25 = calculate_ma_simple(prices, MA_LONG)
            
            if curr_ma7 is not None and curr_ma25 is not None:
                if iteration_count % 10 == 0:
                    usdt_bal, ltc_bal = get_balances()
                    log_message(f"Баланс: {usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC", "BALANCE")
                    bot_status["balance"] = f"{usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC"
                
                current_usdt, current_ltc = get_balances()
                # Определяем основной актив по стоимости, а не только по количеству
                ltc_value = current_ltc * current_price
                current_asset = "LTC" if ltc_value >= MIN_ASSET_VALUE else "USDT"
                ma_direction = "MA7>MA25" if curr_ma7 > curr_ma25 else "MA7<MA25"
                should_have = "LTC" if curr_ma7 > curr_ma25 else "USDT"
                status_emoji = "✅" if current_asset == should_have else "⚠️"
                
                log_message(f"Ціна: {current_price:.4f} | MA7={curr_ma7:.4f}, MA25={curr_ma25:.4f} | {ma_direction} | Актив: {current_asset} {status_emoji} (USDT: {current_usdt:.2f}, LTC: {ltc_value:.2f})", "MA")
                
                bot_status.update({
                    "status": "running",
                    "last_update": datetime.now().isoformat(),
                    "price": current_price,
                    "ma7": curr_ma7,
                    "ma25": curr_ma25,
                    "trend": ma_direction,
                    "current_asset": current_asset
                })
                
                if prev_ma7 is not None:
                    # Постоянная автокоррекция позиции при несоответствии стратегии (не чаще раза в 5 минут)
                    current_time = time.time()
                    if current_time - last_autocorrect_time > 300:  # 5 минут
                        current_price = prices[-1]
                        ltc_current_value = current_ltc * current_price
                        
                        # Определяем нужную позицию по стратегии
                        should_hold_ltc = curr_ma7 > curr_ma25
                        currently_holding_ltc = ltc_current_value >= MIN_ASSET_VALUE
                        
                        # Если позиция не соответствует стратегии - корректируем
                        if should_hold_ltc and not currently_holding_ltc and current_usdt >= MIN_NOTIONAL:
                            log_message("� АВТОКОРРЕКЦИЯ: MA7>MA25, но держим USDT - покупаем LTC", "AUTOCORRECT")
                            place_buy_order(SYMBOL, current_usdt)
                            log_message("� Позиция скорректирована: переход на LTC", "AUTOCORRECT")
                            last_autocorrect_time = current_time
                        elif not should_hold_ltc and currently_holding_ltc and ltc_current_value >= MIN_NOTIONAL:
                            log_message("🔄 АВТОКОРРЕКЦИЯ: MA7<MA25, но держим LTC - продаем LTC", "AUTOCORRECT")
                            place_sell_order(SYMBOL, current_ltc)
                            log_message("💰 Позиция скорректирована: переход на USDT", "AUTOCORRECT")
                            last_autocorrect_time = current_time
                    
                    # Логика торговли на основе пересечений MA
                    if prev_ma7 < prev_ma25 and curr_ma7 > curr_ma25:
                        log_message("📈 Сигнал BUY: MA7 перетнула MA25 вгору", "SIGNAL")
                        if current_usdt >= MIN_NOTIONAL:
                            place_buy_order(SYMBOL, current_usdt)
                        else:
                            log_message(f"   ⚠️ Недостатньо USDT для покупки: {current_usdt:.2f} < {MIN_NOTIONAL}", "WARNING")
                    
                    elif prev_ma7 > prev_ma25 and curr_ma7 < curr_ma25:
                        log_message("📉 Сигнал SELL: MA7 перетнула MA25 вниз", "SIGNAL")
                        current_price = prices[-1]
                        ltc_value = current_ltc * current_price
                        if ltc_value >= MIN_NOTIONAL:
                            place_sell_order(SYMBOL, current_ltc)
                        else:
                            log_message(f"   ⚠️ Недостатньо LTC для продажу: {ltc_value:.2f} USDT < {MIN_NOTIONAL}", "WARNING")

                prev_ma7, prev_ma25 = curr_ma7, curr_ma25
                iteration_count += 1

            if running:
                time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log_message(f"Помилка: {e}", "ERROR")
            bot_status["status"] = f"error: {str(e)}"
            if running:
                time.sleep(CHECK_INTERVAL)
    
    log_message("Бот остановлен", "SHUTDOWN")

# Flask routes
@app.route('/')
def home():
    return jsonify({
        "service": "LTC Trading Bot",
        "status": bot_status["status"],
        "last_update": bot_status.get("last_update"),
        "balance": bot_status.get("balance"),
        "price": bot_status.get("price"),
        "ma7": bot_status.get("ma7"),
        "ma25": bot_status.get("ma25"),
        "trend": bot_status.get("trend"),
        "current_asset": bot_status.get("current_asset")
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "bot_status": bot_status["status"]})

@app.route('/stop')
def stop_bot():
    global running
    running = False
    return jsonify({"message": "Bot stopping..."})

@app.route('/start')
def start_bot():
    global running, bot_thread
    if not client:
        return jsonify({"error": "No API keys configured"}), 400
    
    if running:
        return jsonify({"message": "Bot is already running"})
    
    try:
        running = True
        bot_thread = threading.Thread(target=trading_bot, daemon=True)
        bot_thread.start()
        log_message("Торговый бот запущен через API", "STARTUP")
        return jsonify({"message": "Bot started successfully"})
    except Exception as e:
        running = False
        return jsonify({"error": f"Failed to start bot: {str(e)}"}), 500

@app.route('/status')
def status():
    return jsonify({
        "bot_status": bot_status["status"],
        "running": running,
        "last_update": bot_status.get("last_update"),
        "balance": bot_status.get("balance"),
        "has_api_keys": client is not None
    })

# Автозапуск бота при импорте (для gunicorn)
if client and API_KEY and API_SECRET:
    try:
        if not 'bot_thread' in globals() or bot_thread is None:
            running = True
            bot_thread = threading.Thread(target=trading_bot, daemon=True)
            bot_thread.start()
            log_message("Торговый бот запущен автоматически (gunicorn)", "STARTUP")
    except Exception as e:
        log_message(f"Ошибка автозапуска бота: {e}", "ERROR")
        running = False
else:
    log_message("Автозапуск бота пропущен: нет API ключей", "WARNING")

if __name__ == '__main__':
    # Запускаем торговый бот в отдельном потоке
    if client:
        bot_thread = threading.Thread(target=trading_bot, daemon=True)
        bot_thread.start()
        log_message("Торговый бот запущен в фоне", "STARTUP")
    else:
        log_message("Бот не запущен - нет API ключей", "WARNING")
    
    # Запускаем Flask сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
