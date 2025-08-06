# trading_bot/ltc_bot.py
import os
import time
# import pandas as pd  # Удалили pandas для совместимости с Render
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
SYMBOL = 'LTCUSDT'  # Торгова пара Лайткоін до USDT
INTERVAL = Client.KLINE_INTERVAL_5MINUTE  # Таймфрейм 5 хвилин
MA_SHORT = 7
MA_LONG = 25
CHECK_INTERVAL = 20  # Перевіряти MA кожні 20 секунд (щоб не пропустити пересечення)
TRADE_PERCENTAGE = 0.95  # Використовувати 95% балансу (залишаємо 5% на комісії)
TEST_MODE = False  # Увімкнути для тестування без реальних сделок

# Глобальная переменная для graceful shutdown
running = True

def signal_handler(signum, frame):
    global running
    log_message("Получен сигнал завершения, останавливаем бота...", "SHUTDOWN")
    running = False

# Регистрируем обработчики сигналов
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Логування з часовими мітками
def log_message(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    sys.stdout.flush()  # Принудительная очистка буфера для Render

# Підключення до Binance з автокорекцією часу
try:
    client = Client(API_KEY, API_SECRET)
    # Синхронізація часу з сервером Binance
    server_time = client.get_server_time()
    local_time = int(time.time() * 1000)
    time_offset = server_time['serverTime'] - local_time
    log_message(f"Час сервера Binance: {server_time['serverTime']}", "TIME")
    log_message(f"Локальний час: {local_time}", "TIME")
    log_message(f"Різниця часу: {time_offset}ms", "TIME")
    
    # Встановлюємо offset для синхронізації
    if abs(time_offset) > 500:  # Якщо різниця більше 500ms
        log_message(f"Застосовуємо корекцію часу: {time_offset}ms", "TIME")
        # Додаємо невеликий буфер для безпеки
        client.timestamp_offset = time_offset - 1000  # Віднімаємо 1 секунду для безпеки
    
    client.ping()
    log_message("Підключення до Binance успішне", "SUCCESS")
except Exception as e:
    log_message(f"Помилка підключення до Binance: {e}", "ERROR")
    exit(1)

# Отримання точності та мінімальної кількості лоту
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

# Минимальная стоимость сделки для Binance (обычно 10 USDT)
MIN_NOTIONAL = 10.0

# Получение балансов с обработкой ошибок времени
def get_balances():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            usdt_balance = float(client.get_asset_balance('USDT')['free'])
            ltc_balance = float(client.get_asset_balance('LTC')['free'])
            return usdt_balance, ltc_balance
        except Exception as e:
            if "1021" in str(e) and attempt < max_retries - 1:  # Timestamp error
                log_message(f"Помилка часу (спроба {attempt + 1}/{max_retries}), повтор через 2 сек...", "WARNING")
                time.sleep(2)
                continue
            else:
                log_message(f"Помилка отримання балансу: {e}", "ERROR")
                return 0.0, 0.0

# Логирование баланса
def log_balance():
    usdt_bal, ltc_bal = get_balances()
    log_message(f"Баланс: {usdt_bal:.4f} USDT | {ltc_bal:.6f} LTC", "BALANCE")

# Отримання свічок без pandas
def get_klines(symbol, interval, limit=MA_LONG+5):
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
    """Расчет скользящей средней без pandas"""
    if len(prices) < period:
        return None
    
    # Берем последние period цен и считаем среднее
    recent_prices = prices[-period:]
    return sum(recent_prices) / len(recent_prices)

# Функції купівлі та продажу з retry логікою
def buy(price):
    if TEST_MODE:
        log_message(f"[TEST MODE] Симуляція покупки за {price}", "TEST")
        return
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            usdt_bal = float(client.get_asset_balance('USDT')['free'])
            qty = round((usdt_bal * TRADE_PERCENTAGE) / price, QUANTITY_PRECISION)
            
            # Проверяем минимальную стоимость сделки (NOTIONAL)
            notional_value = usdt_bal * TRADE_PERCENTAGE
            
            log_message(f"Спроба покупки: USDT баланс={usdt_bal:.4f}, ціна={price:.4f}, кількість={qty:.6f}, сума={notional_value:.2f} USDT", "INFO")
            
            if qty >= MIN_QUANTITY and notional_value >= MIN_NOTIONAL:
                order = client.create_order(symbol=SYMBOL, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty)
                
                # Детальна інформація про сделку
                order_id = order['orderId']
                executed_qty = float(order['executedQty'])
                avg_price = float(order['fills'][0]['price']) if order['fills'] else price
                commission = float(order['fills'][0]['commission']) if order['fills'] else 0
                commission_asset = order['fills'][0]['commissionAsset'] if order['fills'] else 'Unknown'
                
                log_message(f"✅ ПОКУПКА ВИКОНАНА:", "ORDER")
                log_message(f"   Order ID: {order_id}", "ORDER")
                log_message(f"   Кількість: {executed_qty:.6f} {SYMBOL[:3]}", "ORDER")
                log_message(f"   Середня ціна: {avg_price:.4f} USDT", "ORDER")
                log_message(f"   Комісія: {commission:.6f} {commission_asset}", "ORDER")
                log_message(f"   Загальна вартість: {executed_qty * avg_price:.4f} USDT", "ORDER")
                
                # Оновлений баланс
                log_balance()
                return
            elif qty < MIN_QUANTITY:
                log_message(f"❌ Занадто мала кількість для покупки: {qty:.6f} < {MIN_QUANTITY}", "WARNING")
                return
            else:
                log_message(f"❌ Занадто мала сума для покупки: {notional_value:.2f} USDT < {MIN_NOTIONAL} USDT", "WARNING")
                return
                
        except Exception as e:
            if "1021" in str(e) and attempt < max_retries - 1:
                log_message(f"Помилка часу при покупці (спроба {attempt + 1}/{max_retries}), повтор через 2 сек...", "WARNING")
                time.sleep(2)
                continue
            else:
                log_message(f"❌ Помилка при покупці: {e}", "ERROR")
                return

def sell(price):
    if TEST_MODE:
        log_message(f"[TEST MODE] Симуляція продажу за {price}", "TEST")
        return
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ltc_bal = float(client.get_asset_balance('LTC')['free'])
            qty = round(ltc_bal, QUANTITY_PRECISION)
            
            # Проверяем минимальную стоимость сделки (NOTIONAL)
            notional_value = qty * price
            
            log_message(f"Спроба продажу: LTC баланс={ltc_bal:.6f}, ціна={price:.4f}, кількість={qty:.6f}, сума={notional_value:.2f} USDT", "INFO")
            
            if qty >= MIN_QUANTITY and notional_value >= MIN_NOTIONAL:
                order = client.create_order(symbol=SYMBOL, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty)
                
                # Детальна інформація про сделку
                order_id = order['orderId']
                executed_qty = float(order['executedQty'])
                avg_price = float(order['fills'][0]['price']) if order['fills'] else price
                commission = float(order['fills'][0]['commission']) if order['fills'] else 0
                commission_asset = order['fills'][0]['commissionAsset'] if order['fills'] else 'Unknown'
                
                log_message(f"✅ ПРОДАЖ ВИКОНАНО:", "ORDER")
                log_message(f"   Order ID: {order_id}", "ORDER")
                log_message(f"   Кількість: {executed_qty:.6f} {SYMBOL[:3]}", "ORDER")
                log_message(f"   Середня ціна: {avg_price:.4f} USDT", "ORDER")
                log_message(f"   Комісія: {commission:.6f} {commission_asset}", "ORDER")
                log_message(f"   Загальна сума: {executed_qty * avg_price:.4f} USDT", "ORDER")
                
                # Оновлений баланс
                log_balance()
                return
            elif qty < MIN_QUANTITY:
                log_message(f"❌ Занадто мала кількість для продажу: {qty:.6f} < {MIN_QUANTITY}", "WARNING")
                return
            else:
                log_message(f"❌ Занадто мала сума для продажу: {notional_value:.2f} USDT < {MIN_NOTIONAL} USDT", "WARNING")
                return
                
        except Exception as e:
            if "1021" in str(e) and attempt < max_retries - 1:
                log_message(f"Помилка часу при продажу (спроба {attempt + 1}/{max_retries}), повтор через 2 сек...", "WARNING")
                time.sleep(2)
                continue
            else:
                log_message(f"❌ Помилка при продажу: {e}", "ERROR")
                return

# Головна функція бота
def run_bot():
    global running
    log_message(f"Старт бота для {SYMBOL} (TEST_MODE: {TEST_MODE})", "STARTUP")
    log_balance()  # Показати початковий баланс
    
    # Автоматичне визначення поточної позиції
    usdt_bal, ltc_bal = get_balances()
    if ltc_bal >= MIN_QUANTITY:
        log_message(f"🔍 Поточна позиція: LTC ({ltc_bal:.6f})", "POSITION")
    else:
        log_message(f"🔍 Поточна позиція: USDT ({usdt_bal:.4f})", "POSITION")
    
    prev_ma7 = prev_ma25 = None
    iteration_count = 0

    while running:
        try:
            prices = get_klines(SYMBOL, INTERVAL)
            current_price = prices[-1]
            
            # Расчет скользящих средних без pandas
            curr_ma7 = calculate_ma_simple(prices, MA_SHORT)
            curr_ma25 = calculate_ma_simple(prices, MA_LONG)

            if curr_ma7 is not None and curr_ma25 is not None:
                # Показываем баланс каждые 10 итераций (каждые ~3.5 минуты)
                if iteration_count % 10 == 0:
                    log_balance()
                
                current_usdt, current_ltc = get_balances()
                current_asset = "LTC" if current_ltc >= MIN_QUANTITY else "USDT"
                ma_direction = "MA7>MA25" if curr_ma7 > curr_ma25 else "MA7<MA25"
                should_have = "LTC" if curr_ma7 > curr_ma25 else "USDT"
                
                status_emoji = "✅" if current_asset == should_have else "⚠️"
                
                log_message(f"Ціна: {current_price:.4f} | MA7={curr_ma7:.4f}, MA25={curr_ma25:.4f} | {ma_direction} | Актив: {current_asset} {status_emoji}", "MA")
                
                if prev_ma7 is not None:
                    # Добавляем детальные логи для диагностики
                    ma7_trend = "↗️" if curr_ma7 > prev_ma7 else "↘️" if curr_ma7 < prev_ma7 else "➡️"
                    ma25_trend = "↗️" if curr_ma25 > prev_ma25 else "↘️" if curr_ma25 < prev_ma25 else "➡️"
                    
                    log_message(f"Тренд: MA7 {ma7_trend} ({prev_ma7:.4f}→{curr_ma7:.4f}) | MA25 {ma25_trend} ({prev_ma25:.4f}→{curr_ma25:.4f})", "TREND")
                    
                    # Одноразовая коррекция позиции при запуске
                    if iteration_count == 1:  # Только на первой итерации после старта
                        current_usdt_bal, current_ltc_bal = get_balances()
                        if curr_ma7 < curr_ma25 and current_ltc_bal >= MIN_QUANTITY:
                            log_message("🔄 АВТОКОРРЕКЦИЯ: MA7<MA25, продаем LTC для выравнивания стратегии", "AUTOCORRECT")
                            sell(current_price)
                            log_message("💰 Позиция скорректирована: переход на USDT", "AUTOCORRECT")
                        elif curr_ma7 > curr_ma25 and current_usdt_bal >= 1.0:
                            log_message("🔄 АВТОКОРРЕКЦИЯ: MA7>MA25, покупаем LTC для выравнивания стратегии", "AUTOCORRECT")
                            buy(current_price)
                            log_message("💰 Позиция скорректирована: переход на LTC", "AUTOCORRECT")
                    
                    # Логика торговли на основе пересечений MA
                    current_ma_position = "ABOVE" if curr_ma7 > curr_ma25 else "BELOW"
                    
                    # BUY сигнал: MA7 пересекает MA25 снизу вверх (должны держать LTC)
                    if prev_ma7 < prev_ma25 and curr_ma7 > curr_ma25:
                        log_message("📈 Сигнал BUY: MA7 перетнула MA25 вгору - переходим на LTC", "SIGNAL")
                        log_message(f"   Детали: prev_ma7={prev_ma7:.4f} < prev_ma25={prev_ma25:.4f}, curr_ma7={curr_ma7:.4f} > curr_ma25={curr_ma25:.4f}", "SIGNAL")
                        # Покупаем LTC если у нас есть USDT
                        usdt_current, ltc_current = get_balances()
                        if usdt_current >= 1.0:  # Минимум 1 USDT для покупки
                            buy(current_price)
                            log_message("💰 Тепер тримаємо LTC (MA7 > MA25)", "STRATEGY")
                        else:
                            log_message("   ⚠️ Недостатньо USDT для покупки", "WARNING")
                    
                    # SELL сигнал: MA7 пересекает MA25 сверху вниз (должны держать USDT)
                    elif prev_ma7 > prev_ma25 and curr_ma7 < curr_ma25:
                        log_message("📉 Сигнал SELL: MA7 перетнула MA25 вниз - переходим на USDT", "SIGNAL")
                        log_message(f"   Детали: prev_ma7={prev_ma7:.4f} > prev_ma25={prev_ma25:.4f}, curr_ma7={curr_ma7:.4f} < curr_ma25={curr_ma25:.4f}", "SIGNAL")
                        # Продаем LTC если у нас есть LTC
                        usdt_current, ltc_current = get_balances()
                        if ltc_current >= MIN_QUANTITY:
                            sell(current_price)
                            log_message("💰 Тепер тримаємо USDT (MA7 < MA25)", "STRATEGY")
                        else:
                            log_message("   ⚠️ Недостатньо LTC для продажу", "WARNING")
                    
                    # Проверка соответствия стратегии
                    usdt_balance, ltc_balance = get_balances()
                    if curr_ma7 > curr_ma25 and ltc_balance < MIN_QUANTITY and usdt_balance >= 1.0:
                        log_message("⚠️ MA7 > MA25, але у нас USDT замість LTC", "STRATEGY_WARNING")
                    elif curr_ma7 < curr_ma25 and ltc_balance >= MIN_QUANTITY:
                        log_message("⚠️ MA7 < MA25, але у нас LTC замість USDT", "STRATEGY_WARNING")
                    
                    # Логируем близкие значения MA (когда они почти пересекаются)
                    ma_diff = abs(curr_ma7 - curr_ma25)
                    ma_diff_pct = (ma_diff / curr_ma25) * 100
                    if ma_diff_pct < 0.1:  # Если разница меньше 0.1%
                        log_message(f"🔄 MA близко к пересечению: разница {ma_diff:.4f} ({ma_diff_pct:.3f}%)", "CROSSOVER")

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
