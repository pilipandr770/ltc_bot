# web_bot.py - Простой спот-бот для переключения между активами по пересечению MA7/MA25
# MA7 > MA25 = держим коин, MA7 < MA25 = держим USDT
import os
import json
import time
import math
import threading
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any
from flask import Flask, jsonify
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException, BinanceOrderException

# ========== Простая логика переключения активов ==========
class AssetSwitcher:
    """Простой класс для переключения между активами по MA сигналам"""
    
    def __init__(self, client: Optional[Client], symbol: str):
        self.client = client
        self.symbol = symbol
        self.base_asset = symbol[:-4] if symbol.endswith("USDT") else symbol.split("USDT")[0]
        self.quote_asset = "USDT"
        self.last_switch_time = 0
        self.min_switch_interval = 10  # минимум 10 секунд между переключениями
    
    def should_hold_base(self, ma_short: float, ma_long: float) -> bool:
        """Определить, должны ли мы держать базовый актив (коин)"""
        return ma_short > ma_long
    
    def get_current_asset_preference(self, usdt_balance: float, base_balance: float, current_price: float) -> str:
        """Определить какой актив мы сейчас держим"""
        usdt_value = usdt_balance
        base_value = base_balance * current_price
        
        # Логируем детали для диагностики
        log(f"🔍 ОПРЕДЕЛЕНИЕ АКТИВА: USDT=${usdt_value:.2f}, {self.base_asset}=${base_value:.2f}", "DEBUG")
        
        # Считаем что держим тот актив, которого больше по стоимости
        # Используем более низкий порог для определения
        if base_value > usdt_value and base_value > 1.0:  # минимум $1
            log(f"🔍 РЕЗУЛЬТАТ: Держим {self.base_asset} (${base_value:.2f} > ${usdt_value:.2f})", "DEBUG")
            return self.base_asset
        else:
            log(f"🔍 РЕЗУЛЬТАТ: Держим {self.quote_asset} (${usdt_value:.2f} >= ${base_value:.2f})", "DEBUG")
            return self.quote_asset
    
    def need_to_switch(self, current_asset: str, should_hold: str) -> bool:
        """Нужно ли переключать актив"""
        current_time = time.time()
        time_since_last = current_time - self.last_switch_time
        
        log(f"🔍 ПРОВЕРКА ПЕРЕКЛЮЧЕНИЯ: current='{current_asset}', should='{should_hold}', time_since_last={time_since_last:.1f}s", "DEBUG")
        
        # Проверяем кулдаун
        if time_since_last < self.min_switch_interval:
            log(f"🔍 КУЛДАУН АКТИВЕН: {time_since_last:.1f}s < {self.min_switch_interval}s", "DEBUG")
            return False
        
        assets_different = current_asset != should_hold
        log(f"🔍 АКТИВЫ РАЗНЫЕ: {assets_different}", "DEBUG")
        
        return assets_different
    
    def execute_switch(self, from_asset: str, to_asset: str, balance: float, current_price: float, step: float) -> bool:
        """Выполнить переключение актива"""
        try:
            if from_asset == self.base_asset and to_asset == self.quote_asset:
                # Продаем коин за USDT
                return self._sell_base_for_usdt(balance, step)
            elif from_asset == self.quote_asset and to_asset == self.base_asset:
                # Покупаем коин за USDT
                return self._buy_base_with_usdt(balance, current_price, step)
            return False
        except Exception as e:
            log(f"Ошибка переключения {from_asset} -> {to_asset}: {e}", "ERROR")
            return False
    
    def _sell_base_for_usdt(self, base_qty: float, step: float) -> bool:
        """Продать весь базовый актив за USDT"""
        if TEST_MODE:
            log(f"🧪 TEST SELL: {base_qty:.6f} {self.base_asset} -> USDT", "TEST")
            self.last_switch_time = time.time()
            return True
        
        if not self.client:
            log(f"❌ Нет подключения к Binance API", "ERROR")
            return False
        
        # Округляем количество согласно требованиям биржи
        qty = round_step(base_qty * 0.999, step)  # 99.9% для учета комиссий
        
        log(f"🔢 РАСЧЕТ ПРОДАЖИ: Исходное количество={base_qty:.6f}, После округления={qty:.6f} (step={step})", "CALC")
        
        if qty <= 0:
            log(f"❌ Количество для продажи слишком мало: {qty:.6f}", "WARN")
            return False
        
        try:
            log(f"📤 ОТПРАВКА ОРДЕРА НА ПРОДАЖУ: {qty:.6f} {self.base_asset}", "ORDER")
            order = self.client.order_market_sell(symbol=self.symbol, quantity=qty)
            
            # Подробная информация об ордере
            if 'fills' in order and order['fills']:
                total_usdt = sum(float(fill['price']) * float(fill['qty']) for fill in order['fills'])
                avg_price = total_usdt / float(order['executedQty']) if float(order['executedQty']) > 0 else 0
                log(f"✅ ПРОДАЖА ВЫПОЛНЕНА: {order['executedQty']} {self.base_asset} за {total_usdt:.2f} USDT (средняя цена: {avg_price:.4f})", "TRADE")
            else:
                log(f"✅ ПРОДАЖА ВЫПОЛНЕНА: {qty:.6f} {self.base_asset} -> USDT", "TRADE")
            
            self.last_switch_time = time.time()
            return True
        except Exception as e:
            log(f"❌ ОШИБКА ПРОДАЖИ: {e}", "ERROR")
            return False
    
    def _buy_base_with_usdt(self, usdt_amount: float, current_price: float, step: float) -> bool:
        """Купить базовый актив за весь USDT"""
        if TEST_MODE:
            qty = usdt_amount / current_price
            log(f"🧪 TEST BUY: {usdt_amount:.2f} USDT -> {qty:.6f} {self.base_asset}", "TEST")
            self.last_switch_time = time.time()
            return True
        
        if not self.client:
            log(f"❌ Нет подключения к Binance API", "ERROR")
            return False
        
        # Рассчитываем количество с учетом комиссий
        usdt_to_spend = usdt_amount * 0.999  # 99.9% для учета комиссий
        qty = round_step(usdt_to_spend / current_price, step)
        
        log(f"🔢 РАСЧЕТ ПОКУПКИ: USDT={usdt_amount:.2f}, К трате={usdt_to_spend:.2f}, Цена={current_price:.4f}, Количество={qty:.6f} (step={step})", "CALC")
        
        if qty <= 0 or usdt_to_spend < 10:  # минимум $10
            log(f"❌ Сумма для покупки слишком мала: {usdt_to_spend:.2f} USDT (минимум $10)", "WARN")
            return False
        
        try:
            log(f"📤 ОТПРАВКА ОРДЕРА НА ПОКУПКУ: {qty:.6f} {self.base_asset} за {usdt_to_spend:.2f} USDT", "ORDER")
            order = self.client.order_market_buy(symbol=self.symbol, quantity=qty)
            
            # Подробная информация об ордере
            if 'fills' in order and order['fills']:
                total_cost = sum(float(fill['price']) * float(fill['qty']) for fill in order['fills'])
                avg_price = total_cost / float(order['executedQty']) if float(order['executedQty']) > 0 else 0
                log(f"✅ ПОКУПКА ВЫПОЛНЕНА: {order['executedQty']} {self.base_asset} за {total_cost:.2f} USDT (средняя цена: {avg_price:.4f})", "TRADE")
            else:
                log(f"✅ ПОКУПКА ВЫПОЛНЕНА: {usdt_to_spend:.2f} USDT -> {qty:.6f} {self.base_asset}", "TRADE")
            
            self.last_switch_time = time.time()
            return True
        except Exception as e:
            log(f"❌ ОШИБКА ПОКУПКИ: {e}", "ERROR")
            return False

# ========== Загрузка окружения ==========
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY", "").strip() or None
API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip() or None
SYMBOL = os.getenv("SYMBOL", "BNBUSDT").upper()
INTERVAL = os.getenv("INTERVAL", "5m")  # 1m,3m,5m,15m,1h,...
MA_SHORT = int(os.getenv("MA_SHORT", "7"))
MA_LONG = int(os.getenv("MA_LONG", "25"))

# Основные параметры
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "20"))   # проверка каждые 20 секунд
STATE_PATH = os.getenv("STATE_PATH", "state.json")

# Фильтр шума для кроса (мин. разница между MA в % от цены)
MA_SPREAD_BPS = float(os.getenv("MA_SPREAD_BPS", "2.0"))  # 2 б.п. = 0.02% для более чувствительной торговли

# Дополнительные параметры
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))
MIN_BALANCE_USDT = float(os.getenv("MIN_BALANCE_USDT", "10.0"))

app = Flask(__name__)

# Глобальные переменные
client: Optional[Client] = None
asset_switcher: Optional[AssetSwitcher] = None
running = False
last_action_ts = 0
last_health_check = 0
error_count = 0

bot_status = {
    "status": "idle", 
    "symbol": SYMBOL, 
    "current_asset": "USDT",  # какой актив держим сейчас
    "should_hold": "USDT",    # какой актив должны держать по стратегии
    "test_mode": TEST_MODE,
    "last_update": None,
    "balance_usdt": 0.0,
    "balance_base": 0.0,
    "current_price": 0.0,
    "ma_short": 0.0,
    "ma_long": 0.0,
    "error_count": 0,
    "uptime": 0,
    "last_switch": None,
    "switches_count": 0
}

# ========== Утилиты логов ==========
def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

# ========== Персистентное состояние ==========
def load_state():
    global bot_status
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                bot_status.update(data)
                log("Состояние загружено из state.json", "STATE")
        except Exception as e:
            log(f"Не удалось загрузить состояние: {e}", "WARN")

def save_state():
    try:
        bot_status["last_update"] = datetime.now(timezone.utc).isoformat()
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(bot_status, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Не удалось сохранить состояние: {e}", "WARN")

# ========== Binance клиент ==========
def init_client():
    global client, asset_switcher
    if API_KEY and API_SECRET:
        try:
            client = Client(API_KEY, API_SECRET)
            # синхронизация времени
            server_time = client.get_server_time()
            local_time = int(time.time() * 1000)
            offset = server_time["serverTime"] - local_time
            if abs(offset) > 1000:
                client.timestamp_offset = offset
                log(f"Время синхронизировано, offset={offset}мс", "TIME")
            
            client.ping()
            asset_switcher = AssetSwitcher(client, SYMBOL)
            
            log("Подключение к Binance успешно", "SUCCESS")
            bot_status["status"] = "connected"
            return True
        except Exception as e:
            log(f"Ошибка подключения к Binance: {e}", "ERROR")
            client = None
            asset_switcher = None
            bot_status["status"] = "connection_error"
            return False
    else:
        log("API ключи не заданы — TEST_MODE автоматически true", "WARN")
        asset_switcher = AssetSwitcher(None, SYMBOL)
        bot_status["status"] = "no_api_keys"
        return False

# ========== Информация по символу и округление ==========
def get_symbol_filters(symbol: str):
    if not client:
        return 0.001, 0.01, 0.001, 10.0
    
    try:
        info = client.get_symbol_info(symbol)
        if not info:
            raise RuntimeError(f"Не найден символ {symbol}")
        
        lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
        pricef = next(f for f in info["filters"] if f["filterType"] == "PRICE_FILTER")
        min_notional = next((f for f in info["filters"] if f["filterType"] == "MIN_NOTIONAL"), None)
        
        step = float(lot["stepSize"])
        tick = float(pricef["tickSize"])
        min_qty = float(lot["minQty"])
        min_not = float(min_notional["minNotional"]) if min_notional else 10.0
        
        return step, tick, min_qty, min_not
    except Exception as e:
        log(f"Ошибка получения фильтров символа: {e}", "ERROR")
        return 0.001, 0.01, 0.001, 10.0

def round_step(qty: float, step: float) -> float:
    return math.floor(qty / step) * step

def round_tick(price: float, tick: float) -> float:
    return round(math.floor(price / tick) * tick, 8)

def retry_on_error(func, max_retries=MAX_RETRIES, delay=1):
    """Повторяет выполнение функции при ошибках"""
    for attempt in range(max_retries):
        try:
            return func()
        except (BinanceAPIException, BinanceOrderException) as e:
            if "Too many requests" in str(e) or "Request rate limit" in str(e):
                wait_time = delay * (2 ** attempt)
                log(f"Rate limit, ждем {wait_time}с (попытка {attempt + 1}/{max_retries})", "WARN")
                time.sleep(wait_time)
            else:
                log(f"Binance ошибка (попытка {attempt + 1}/{max_retries}): {e}", "ERROR")
                if attempt < max_retries - 1:
                    time.sleep(delay)
        except Exception as e:
            log(f"Неожиданная ошибка (попытка {attempt + 1}/{max_retries}): {e}", "ERROR")
            if attempt < max_retries - 1:
                time.sleep(delay)
    
    raise RuntimeError(f"Не удалось выполнить операцию после {max_retries} попыток")

# ========== Данные и MA ==========
BINANCE_INTERVALS = {
    "1m": Client.KLINE_INTERVAL_1MINUTE,
    "3m": Client.KLINE_INTERVAL_3MINUTE,
    "5m": Client.KLINE_INTERVAL_5MINUTE,
    "15m": Client.KLINE_INTERVAL_15MINUTE,
    "1h": Client.KLINE_INTERVAL_1HOUR,
    "4h": Client.KLINE_INTERVAL_4HOUR,
}

def get_closes(symbol: str, interval: str, limit: int = 200):
    if not client:
        import random
        base_price = 600.0 if symbol == "BNBUSDT" else 100.0
        return [base_price + random.uniform(-5, 5) for _ in range(limit)]
    
    def _get_klines():
        inter = BINANCE_INTERVALS.get(interval, Client.KLINE_INTERVAL_5MINUTE)
        klines = client.get_klines(symbol=symbol, interval=inter, limit=limit)
        return [float(k[4]) for k in klines]
    
    return retry_on_error(_get_klines)

def ma(arr, period):
    if len(arr) < period:
        return None
    return sum(arr[-period:]) / period

# ========== Балансы ==========
def get_balances() -> Tuple[float, float]:
    if not client:
        return 1000.0, 0.0
    
    def _get_balances():
        base = SYMBOL[:-4] if SYMBOL.endswith("USDT") else SYMBOL.split("USDT")[0]
        usdt = float(client.get_asset_balance("USDT")["free"])
        base_bal = float(client.get_asset_balance(base)["free"])
        return usdt, base_bal
    
    return retry_on_error(_get_balances)

# ========== Проверка здоровья системы ==========
def health_check():
    global last_health_check, error_count
    current_time = time.time()
    
    if current_time - last_health_check > HEALTH_CHECK_INTERVAL:
        try:
            if client:
                client.ping()
                usdt_bal, base_bal = get_balances()
                bot_status.update({
                    "balance_usdt": usdt_bal,
                    "balance_base": base_bal,
                    "error_count": error_count
                })
                
                if error_count > 0:
                    error_count = max(0, error_count - 1)
                    
            last_health_check = current_time
            log("Проверка здоровья системы пройдена", "HEALTH")
        except Exception as e:
            log(f"Ошибка проверки здоровья: {e}", "ERROR")
            error_count += 1

# ========== Основной торговый цикл ==========
def trading_loop():
    global running, last_action_ts, bot_status, error_count
    
    start_time = time.time()
    log(f"Старт торгового цикла для {SYMBOL} (TEST_MODE={TEST_MODE})", "START")
    
    # Убеждаемся что running = True
    if not running:
        log("⚠️ running=False, устанавливаем в True", "WARN")
        running = True
    
    # Получаем фильтры символа
    step, tick, min_qty, min_notional = get_symbol_filters(SYMBOL)
    load_state()
    
    # Инициализируем asset_switcher если не инициализирован
    global asset_switcher
    if asset_switcher is None:
        log("🔧 Инициализация AssetSwitcher...", "INIT")
        asset_switcher = AssetSwitcher(client, SYMBOL)
    
    cycle_count = 0
    log(f"🔄 Начинаем основной цикл торговли (running={running})", "LOOP")
    
    while running:
        try:
            cycle_count += 1
            log(f"🔄 ЦИКЛ #{cycle_count} ==========================================", "CYCLE")
            
            # Обновляем время работы
            bot_status["uptime"] = int(time.time() - start_time)
            
            # Проверка здоровья системы
            health_check()
            
            # Получаем данные
            log("📊 Получение рыночных данных...", "DATA")
            prices = get_closes(SYMBOL, INTERVAL, limit=max(MA_LONG * 3, 100))
            price = prices[-1]
            usdt_bal, base_bal = get_balances()
            
            # Подробный лог балансов
            base_value = base_bal * price
            total_value = usdt_bal + base_value
            log(f"💰 БАЛАНСЫ: USDT={usdt_bal:.2f} | {asset_switcher.base_asset}={base_bal:.6f} (${base_value:.2f}) | ВСЕГО=${total_value:.2f}", "BALANCE")
            
            # Обновляем статус
            bot_status.update({
                "current_price": price,
                "balance_usdt": usdt_bal,
                "balance_base": base_bal
            })
            
            # Проверяем минимальный баланс
            if total_value < MIN_BALANCE_USDT:
                log(f"❌ Недостаточный общий баланс для торговли: ${total_value:.2f} < ${MIN_BALANCE_USDT}", "WARN")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # Рассчитываем MA
            m1 = ma(prices, MA_SHORT)
            m2 = ma(prices, MA_LONG)
            
            if m1 is not None and m2 is not None:
                # Подробный лог MA
                ma_diff = m1 - m2
                ma_diff_pct = (ma_diff / price) * 100
                spread_bps = abs(ma_diff / price) * 10000.0
                
                log(f"📈 MA АНАЛИЗ: MA7={m1:.4f} | MA25={m2:.4f} | Разница={ma_diff:+.4f} ({ma_diff_pct:+.3f}%) | Спред={spread_bps:.1f}б.п.", "MA")
                
                bot_status.update({
                    "ma_short": m1,
                    "ma_long": m2
                })
                
                # Проверяем что asset_switcher инициализирован
                if asset_switcher is None:
                    log("❌ AssetSwitcher не инициализирован", "ERROR")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Определяем какой актив должны держать
                should_hold_base = asset_switcher.should_hold_base(m1, m2)
                should_hold_asset = asset_switcher.base_asset if should_hold_base else asset_switcher.quote_asset
                
                # Определяем какой актив держим сейчас
                current_asset = asset_switcher.get_current_asset_preference(usdt_bal, base_bal, price)
                
                # Подробный лог стратегии
                trend_direction = "ВОСХОДЯЩИЙ 📈" if m1 > m2 else "НИСХОДЯЩИЙ 📉"
                strategy_reason = f"MA7 {'>' if m1 > m2 else '<'} MA25"
                log(f"🎯 СТРАТЕГИЯ: {trend_direction} ({strategy_reason}) → Должны держать {should_hold_asset}", "STRATEGY")
                log(f"🏦 ТЕКУЩИЙ АКТИВ: {current_asset} (по балансам: USDT=${usdt_bal:.2f}, {asset_switcher.base_asset}=${base_value:.2f})", "CURRENT")
                
                # Обновляем статус
                bot_status.update({
                    "current_asset": current_asset,
                    "should_hold": should_hold_asset
                })
                
                # Проверяем фильтр шума
                if spread_bps < MA_SPREAD_BPS:
                    log(f"🔇 ФИЛЬТР ШУМА: Спред {spread_bps:.1f}б.п. < {MA_SPREAD_BPS}б.п. - сигнал слишком слабый", "FILTER")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Проверяем кулдаун
                time_since_last_switch = time.time() - asset_switcher.last_switch_time
                if time_since_last_switch < asset_switcher.min_switch_interval:
                    remaining_cooldown = asset_switcher.min_switch_interval - time_since_last_switch
                    log(f"⏰ КУЛДАУН: Осталось {remaining_cooldown:.1f}сек до следующего переключения", "COOLDOWN")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # Итоговый статус
                status_emoji = "✅ СИНХРОНИЗИРОВАНО" if current_asset == should_hold_asset else "⚠️ ТРЕБУЕТСЯ ПЕРЕКЛЮЧЕНИЕ"
                log(f"📊 СТАТУС: Цена={price:.4f} | Держим={current_asset} | Нужно={should_hold_asset} | {status_emoji}", "STATUS")
                
                # Подробная диагностика переключения
                log(f"🔍 ДИАГНОСТИКА: current_asset='{current_asset}', should_hold_asset='{should_hold_asset}'", "DEBUG")
                log(f"🔍 БАЛАНСЫ: USDT={usdt_bal:.2f}, {asset_switcher.base_asset}={base_bal:.6f} (${base_value:.2f})", "DEBUG")
                log(f"🔍 КУЛДАУН: Прошло {time_since_last_switch:.1f}сек с последнего переключения (мин: {asset_switcher.min_switch_interval}сек)", "DEBUG")
                
                # Проверяем нужно ли переключать актив
                need_switch = asset_switcher.need_to_switch(current_asset, should_hold_asset)
                log(f"🔍 РЕШЕНИЕ: need_to_switch = {need_switch}", "DEBUG")
                
                if need_switch:
                    log(f"🔄 ПЕРЕКЛЮЧЕНИЕ ТРЕБУЕТСЯ: {current_asset} → {should_hold_asset}", "SWITCH")
                    
                    # Подробная информация о переключении
                    if current_asset == asset_switcher.base_asset:
                        # Продаем базовый актив
                        log(f"📉 ПРОДАЖА: {base_bal:.6f} {asset_switcher.base_asset} → USDT по цене {price:.4f}", "TRADE_PLAN")
                        expected_usdt = base_bal * price * 0.999  # с учетом комиссии
                        log(f"💵 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: ~{expected_usdt:.2f} USDT (с учетом комиссии 0.1%)", "TRADE_PLAN")
                        
                        success = asset_switcher.execute_switch(
                            current_asset, should_hold_asset, base_bal, price, step
                        )
                    else:
                        # Покупаем базовый актив
                        log(f"📈 ПОКУПКА: {usdt_bal:.2f} USDT → {asset_switcher.base_asset} по цене {price:.4f}", "TRADE_PLAN")
                        expected_qty = (usdt_bal * 0.999) / price  # с учетом комиссии
                        log(f"🪙 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: ~{expected_qty:.6f} {asset_switcher.base_asset} (с учетом комиссии 0.1%)", "TRADE_PLAN")
                        
                        success = asset_switcher.execute_switch(
                            current_asset, should_hold_asset, usdt_bal, price, step
                        )
                    
                    if success:
                        bot_status["switches_count"] = bot_status.get("switches_count", 0) + 1
                        bot_status["last_switch"] = datetime.now(timezone.utc).isoformat()
                        last_action_ts = time.time()
                        log(f"✅ ПЕРЕКЛЮЧЕНИЕ ВЫПОЛНЕНО УСПЕШНО! Общее количество переключений: {bot_status['switches_count']}", "SUCCESS")
                        
                        # Ждем немного для обновления балансов на бирже
                        time.sleep(2)
                        
                        # Логируем новые балансы после переключения
                        new_usdt_bal, new_base_bal = get_balances()
                        new_base_value = new_base_bal * price
                        new_total = new_usdt_bal + new_base_value
                        log(f"💰 НОВЫЕ БАЛАНСЫ: USDT={new_usdt_bal:.2f} | {asset_switcher.base_asset}={new_base_bal:.6f} (${new_base_value:.2f}) | ВСЕГО=${new_total:.2f}", "RESULT")
                        
                        # Обновляем статус с новыми балансами
                        bot_status.update({
                            "balance_usdt": new_usdt_bal,
                            "balance_base": new_base_bal
                        })
                    else:
                        log(f"❌ ОШИБКА ПЕРЕКЛЮЧЕНИЯ!", "ERROR")
                        error_count += 1
                else:
                    log(f"✅ ПЕРЕКЛЮЧЕНИЕ НЕ ТРЕБУЕТСЯ - активы синхронизированы", "OK")
            
            # Обновляем статус
            bot_status["status"] = "running"
            save_state()
            
            log(f"😴 ОЖИДАНИЕ {CHECK_INTERVAL} секунд до следующего цикла...", "SLEEP")
            time.sleep(CHECK_INTERVAL)
            
        except (BinanceAPIException, BinanceOrderException) as e:
            emsg = str(e)
            if "Too many requests" in emsg or "Request rate limit" in emsg:
                log(f"Rate limit: {e} — сплю 5 сек", "WARN")
                time.sleep(5)
            else:
                log(f"Binance ошибка: {e}", "ERROR")
                error_count += 1
                time.sleep(2)
        except Exception as e:
            log(f"Неожиданная ошибка: {e}", "ERROR")
            error_count += 1
            bot_status["status"] = f"error: {str(e)}"
            save_state()
            time.sleep(2)
    
    log("Торговый бот остановлен", "SHUTDOWN")

# ========== Flask маршруты ==========
@app.route("/")
def root():
    return jsonify({
        "ok": True, 
        "symbol": SYMBOL, 
        "status": bot_status.get("status", "idle"), 
        "current_asset": bot_status.get("current_asset", "USDT"),
        "should_hold": bot_status.get("should_hold", "USDT"),
        "test_mode": TEST_MODE,
        "uptime": bot_status.get("uptime", 0)
    })

@app.route("/health")
def health():
    try:
        if client:
            client.ping()
            return jsonify({"ok": True, "status": "healthy"})
        else:
            return jsonify({"ok": True, "status": "test_mode"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/start")
def start():
    global running, bot_status
    if running:
        return jsonify({"ok": True, "message": "уже работает"})
    
    if API_KEY and API_SECRET:
        init_client()
    
    running = True
    bot_status["status"] = "running"
    save_state()
    
    t = threading.Thread(target=trading_loop, daemon=True)
    t.start()
    log("Бот запущен", "START")
    return jsonify({"ok": True, "mode": "TEST" if TEST_MODE else "LIVE"})

@app.route("/stop")
def stop():
    global running, bot_status
    running = False
    bot_status["status"] = "stopped"
    save_state()
    log("Бот остановлен", "STOP")
    return jsonify({"ok": True})

@app.route("/status")
def status():
    return jsonify({
        "ok": True,
        "symbol": SYMBOL,
        "mode": "TEST" if TEST_MODE else "LIVE",
        "status": bot_status.get("status", "idle"),
        "current_asset": bot_status.get("current_asset", "USDT"),
        "should_hold": bot_status.get("should_hold", "USDT"),
        "current_price": bot_status.get("current_price", 0.0),
        "balance_usdt": bot_status.get("balance_usdt", 0.0),
        "balance_base": bot_status.get("balance_base", 0.0),
        "ma_short": bot_status.get("ma_short", 0.0),
        "ma_long": bot_status.get("ma_long", 0.0),
        "error_count": bot_status.get("error_count", 0),
        "uptime": bot_status.get("uptime", 0),
        "switches_count": bot_status.get("switches_count", 0),
        "last_switch": bot_status.get("last_switch"),
        "last_update": bot_status.get("last_update")
    })

@app.route("/config")
def config():
    return jsonify({
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "ma_short": MA_SHORT,
        "ma_long": MA_LONG,
        "test_mode": TEST_MODE,
        "check_interval": CHECK_INTERVAL,
        "ma_spread_bps": MA_SPREAD_BPS,
        "min_balance_usdt": MIN_BALANCE_USDT
    })

# ========== Автозапуск для деплоя ==========
if API_KEY and API_SECRET:
    try:
        if not running:
            init_client()
            running = True
            bot_thread = threading.Thread(target=trading_loop, daemon=True)
            bot_thread.start()
            mode = "TEST" if TEST_MODE else "LIVE"
            log(f"🚀 Торговый бот запущен автоматически в режиме {mode}", "STARTUP")
    except Exception as e:
        log(f"❌ Ошибка автозапуска бота: {e}", "ERROR")
        running = False
else:
    log("⚠️ Автозапуск бота пропущен: нет API ключей", "WARNING")

# ========== Точка входа ==========
if __name__ == "__main__":
    if API_KEY and API_SECRET:
        init_client()
        
        # Запускаем торговый бот в отдельном потоке
        if not running:
            running = True
            bot_thread = threading.Thread(target=trading_loop, daemon=True)
            bot_thread.start()
            mode = "TEST" if TEST_MODE else "LIVE"
            log(f"🚀 Торговый бот запущен в режиме {mode}", "STARTUP")
    
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
    