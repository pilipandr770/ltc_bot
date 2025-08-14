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

# ========== Утилиты логов ==========
def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

# ========== Управление конфигурацией ==========
from dataclasses import dataclass
from typing import List

@dataclass
class ConfigurationStatus:
    test_mode: bool
    api_keys_present: bool
    api_keys_valid: bool
    environment_source: str  # "system", "file", "default"
    configuration_issues: List[str]
    safety_checks_passed: bool

@dataclass
class TradingModeStatus:
    current_mode: str  # "TEST" or "LIVE"
    mode_source: str   # откуда взято значение
    can_switch_to_live: bool
    blocking_issues: List[str]
    last_mode_change: Optional[datetime]

class EnvironmentConfig:
    """Централизованное управление переменными окружения"""
    
    def __init__(self):
        self.config_status = None
        self.load_environment()
        self.validate_configuration()
    
    def load_environment(self):
        """Загрузка переменных окружения с правильным приоритетом"""
        log("🚀 НАЧАЛО ЗАГРУЗКИ КОНФИГУРАЦИИ", "CONFIG")
        log("=" * 60, "CONFIG")
        
        # Загружаем переменные из .env файла
        # Определяем путь к .env файлу относительно текущего файла
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_file_path = os.path.join(current_dir, '.env')
        
        log(f"🔍 Поиск .env файла: {env_file_path}", "CONFIG")
        if os.path.exists(env_file_path):
            log("✅ .env файл найден, загружаем...", "CONFIG")
            load_dotenv(env_file_path)
        else:
            log("⚠️ .env файл не найден, используем системные переменные", "CONFIG")
            load_dotenv()  # Попытка загрузить из текущей директории
        
        # Загружаем все переменные с логированием
        self.api_key = self._get_env_with_logging("BINANCE_API_KEY", "").strip() or None
        self.api_secret = self._get_env_with_logging("BINANCE_API_SECRET", "").strip() or None
        self.symbol = self._get_env_with_logging("SYMBOL", "BNBUSDT", str.upper)
        self.interval = self._get_env_with_logging("INTERVAL", "30m")
        self.ma_short = self._get_env_with_logging("MA_SHORT", "7", int)
        self.ma_long = self._get_env_with_logging("MA_LONG", "25", int)
        
        # Критически важная переменная TEST_MODE
        # ВАЖНО: По умолчанию используем тестовый режим для безопасности
        # В продакшн среде ОБЯЗАТЕЛЬНО должна быть установлена переменная TEST_MODE=false
        test_mode_str = self._get_env_with_logging("TEST_MODE", "true")
        self.test_mode = test_mode_str.lower() == "true"
        
        # Дополнительная диагностика для TEST_MODE
        log("🔍 ДИАГНОСТИКА TEST_MODE:", "CONFIG")
        log(f"   Сырое значение: '{test_mode_str}'", "CONFIG")
        log(f"   После обработки: {self.test_mode}", "CONFIG")
        log(f"   Ожидаемое для реального режима: TEST_MODE=false", "CONFIG")
        
        # Остальные параметры
        self.check_interval = self._get_env_with_logging("CHECK_INTERVAL", "60", int)
        self.state_path = self._get_env_with_logging("STATE_PATH", "state.json")
        self.ma_spread_bps = self._get_env_with_logging("MA_SPREAD_BPS", "2.0", float)
        self.max_retries = self._get_env_with_logging("MAX_RETRIES", "3", int)
        self.health_check_interval = self._get_env_with_logging("HEALTH_CHECK_INTERVAL", "300", int)
        self.min_balance_usdt = self._get_env_with_logging("MIN_BALANCE_USDT", "10.0", float)
        
        log("✅ КОНФИГУРАЦИЯ ЗАГРУЖЕНА УСПЕШНО", "CONFIG")
        log("=" * 60, "CONFIG")
    
    def _get_env_with_logging(self, name: str, default: str, convert_func=None):
        """Получение переменной окружения с подробным логированием"""
        # Проверяем системные переменные окружения
        system_value = os.environ.get(name)
        
        # Получаем значение из os.getenv (уже загружено через load_dotenv)
        dotenv_value = os.getenv(name)
        
        # Определяем источник и финальное значение
        if system_value is not None:
            final_value = system_value
            source = "системные переменные окружения"
        elif dotenv_value is not None:
            final_value = dotenv_value
            source = ".env файл"
        else:
            final_value = default
            source = "значение по умолчанию"
        
        # Применяем конвертацию если нужно
        if convert_func:
            try:
                converted_value = convert_func(final_value)
                self._log_env_var(name, converted_value, convert_func(default) if default else None, source)
                return converted_value
            except (ValueError, TypeError) as e:
                log(f"❌ Ошибка конвертации {name}={final_value}: {e}. Используется значение по умолчанию.", "ERROR")
                converted_default = convert_func(default) if default else None
                self._log_env_var(name, converted_default, converted_default, "значение по умолчанию (ошибка конвертации)")
                return converted_default
        else:
            self._log_env_var(name, final_value, default, source)
            return final_value
    
    def _log_env_var(self, name: str, value: Any, default: Any, source: str = "unknown") -> None:
        """Логирование переменной окружения с источником"""
        if value == default:
            log(f"🔧 ENV {name}={value} (источник: значение по умолчанию)", "CONFIG")
        else:
            log(f"🔧 ENV {name}={value} (источник: {source})", "CONFIG")
    
    def validate_configuration(self):
        """Валидация критических настроек"""
        issues = []
        
        # Проверяем API ключи
        api_keys_present = bool(self.api_key and self.api_secret)
        if not api_keys_present:
            issues.append("API ключи не настроены")
        
        # Логируем критически важную информацию о режиме торговли
        log("=" * 60, "CONFIG")
        if self.test_mode:
            log("🧪 РЕЖИМ ТОРГОВЛИ: ТЕСТОВЫЙ (TEST_MODE=true)", "CONFIG")
            log("⚠️  Все торговые операции будут симулированы", "CONFIG")
        else:
            log("🔴 РЕЖИМ ТОРГОВЛИ: РЕАЛЬНЫЙ (TEST_MODE=false)", "CONFIG")
            log("⚠️  ВНИМАНИЕ: Будут выполняться РЕАЛЬНЫЕ торговые операции!", "CONFIG")
            log("💰 Убедитесь что API ключи настроены корректно", "CONFIG")
            if not api_keys_present:
                log("❌ КРИТИЧЕСКАЯ ОШИБКА: API ключи не настроены для реального режима!", "ERROR")
                issues.append("Реальный режим требует API ключи")
        log("=" * 60, "CONFIG")
        
        # Создаем статус конфигурации
        self.config_status = ConfigurationStatus(
            test_mode=self.test_mode,
            api_keys_present=api_keys_present,
            api_keys_valid=False,  # Будет проверено позже
            environment_source="mixed",  # Смешанный источник
            configuration_issues=issues,
            safety_checks_passed=len(issues) == 0
        )
    
    def get_trading_mode(self) -> bool:
        """Определение режима торговли с диагностикой"""
        return self.test_mode
    
    def log_configuration_status(self):
        """Подробное логирование текущей конфигурации"""
        if self.config_status:
            log("📊 СТАТУС КОНФИГУРАЦИИ:", "CONFIG")
            log(f"   Режим торговли: {'ТЕСТОВЫЙ' if self.config_status.test_mode else 'РЕАЛЬНЫЙ'}", "CONFIG")
            log(f"   API ключи присутствуют: {'✅' if self.config_status.api_keys_present else '❌'}", "CONFIG")
            log(f"   Проверки безопасности: {'✅' if self.config_status.safety_checks_passed else '❌'}", "CONFIG")
            if self.config_status.configuration_issues:
                log(f"   Проблемы: {', '.join(self.config_status.configuration_issues)}", "CONFIG")

class TradingModeController:
    """Контроллер режима торговли с проверками безопасности"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.test_mode = config.get_trading_mode()
        self.trading_mode_status = None
        self._update_trading_mode_status()
    
    def _update_trading_mode_status(self):
        """Обновление статуса режима торговли"""
        blocking_issues = []
        can_switch_to_live = True
        
        # Проверяем API ключи для реального режима
        if not self.test_mode and not self.config.config_status.api_keys_present:
            blocking_issues.append("API ключи не настроены")
            can_switch_to_live = False
        
        # Проверяем общие проблемы конфигурации
        if self.config.config_status.configuration_issues:
            blocking_issues.extend(self.config.config_status.configuration_issues)
            can_switch_to_live = False
        
        self.trading_mode_status = TradingModeStatus(
            current_mode="TEST" if self.test_mode else "LIVE",
            mode_source="конфигурация окружения",
            can_switch_to_live=can_switch_to_live,
            blocking_issues=blocking_issues,
            last_mode_change=datetime.now(timezone.utc)
        )
    
    def is_test_mode(self) -> bool:
        """Проверка текущего режима торговли"""
        return self.test_mode
    
    def is_live_mode(self) -> bool:
        """Проверка реального режима торговли"""
        return not self.test_mode
    
    def validate_live_mode_requirements(self) -> bool:
        """Проверка требований для реального режима"""
        if self.test_mode:
            return True  # В тестовом режиме все требования выполнены
        
        # Проверяем API ключи
        if not self.config.config_status.api_keys_present:
            log("❌ ПРОВЕРКА РЕАЛЬНОГО РЕЖИМА: API ключи не настроены", "ERROR")
            return False
        
        # Проверяем общие проблемы конфигурации
        if self.config.config_status.configuration_issues:
            log(f"❌ ПРОВЕРКА РЕАЛЬНОГО РЕЖИМА: {', '.join(self.config.config_status.configuration_issues)}", "ERROR")
            return False
        
        log("✅ ПРОВЕРКА РЕАЛЬНОГО РЕЖИМА: Все требования выполнены", "SUCCESS")
        return True
    
    def get_mode_display_name(self) -> str:
        """Получить отображаемое имя режима"""
        return "ТЕСТОВЫЙ" if self.test_mode else "РЕАЛЬНЫЙ"
    
    def get_mode_emoji(self) -> str:
        """Получить эмодзи для режима"""
        return "🧪" if self.test_mode else "🔴"
    
    def log_trading_mode_status(self):
        """Логирование статуса режима торговли"""
        if self.trading_mode_status:
            log("📊 СТАТУС РЕЖИМА ТОРГОВЛИ:", "CONFIG")
            log(f"   Текущий режим: {self.get_mode_emoji()} {self.trading_mode_status.current_mode}", "CONFIG")
            log(f"   Источник: {self.trading_mode_status.mode_source}", "CONFIG")
            log(f"   Можно переключить в реальный: {'✅' if self.trading_mode_status.can_switch_to_live else '❌'}", "CONFIG")
            if self.trading_mode_status.blocking_issues:
                log(f"   Блокирующие проблемы: {', '.join(self.trading_mode_status.blocking_issues)}", "CONFIG")
    
    def get_trade_operation_prefix(self) -> str:
        """Получить префикс для торговых операций"""
        return "🧪 TEST" if self.test_mode else "🔴 LIVE"

class SafetyValidator:
    """Валидатор безопасности для проверок перед торговлей"""
    
    def __init__(self, config: EnvironmentConfig):
        self.config = config
    
    def validate_api_keys(self, api_key: str, api_secret: str) -> bool:
        """Проверка валидности API ключей"""
        if not api_key or not api_secret:
            log("❌ ПРОВЕРКА API КЛЮЧЕЙ: Ключи не предоставлены", "SAFETY")
            return False
        
        # Проверка формата ключей
        if len(api_key) < 20 or len(api_secret) < 20:
            log("❌ ПРОВЕРКА API КЛЮЧЕЙ: Ключи слишком короткие", "SAFETY")
            return False
        
        # Проверка на наличие недопустимых символов
        import re
        if not re.match(r'^[A-Za-z0-9]+$', api_key) or not re.match(r'^[A-Za-z0-9]+$', api_secret):
            log("❌ ПРОВЕРКА API КЛЮЧЕЙ: Ключи содержат недопустимые символы", "SAFETY")
            return False
        
        log("✅ ПРОВЕРКА API КЛЮЧЕЙ: Формат ключей корректный", "SAFETY")
        return True
    
    def check_account_permissions(self, client) -> bool:
        """Проверка разрешений аккаунта для торговли"""
        if not client:
            log("❌ ПРОВЕРКА РАЗРЕШЕНИЙ: Клиент не инициализирован", "SAFETY")
            return False
        
        try:
            # Проверяем статус аккаунта
            account_info = client.get_account()
            
            # Проверяем разрешения на торговлю
            can_trade = account_info.get('canTrade', False)
            if not can_trade:
                log("❌ ПРОВЕРКА РАЗРЕШЕНИЙ: Торговля запрещена для аккаунта", "SAFETY")
                return False
            
            # Проверяем статус аккаунта
            account_type = account_info.get('accountType', 'UNKNOWN')
            log(f"✅ ПРОВЕРКА РАЗРЕШЕНИЙ: Тип аккаунта: {account_type}, торговля разрешена", "SAFETY")
            return True
            
        except Exception as e:
            log(f"❌ ПРОВЕРКА РАЗРЕШЕНИЙ: Ошибка при проверке аккаунта: {e}", "SAFETY")
            return False
    
    def validate_minimum_balance(self, usdt_balance: float, base_balance: float, current_price: float) -> bool:
        """Проверка минимального баланса"""
        total_value = usdt_balance + (base_balance * current_price)
        min_required = self.config.min_balance_usdt
        
        if total_value < min_required:
            log(f"❌ ПРОВЕРКА БАЛАНСА: Недостаточный баланс ${total_value:.2f} < ${min_required:.2f}", "SAFETY")
            return False
        
        log(f"✅ ПРОВЕРКА БАЛАНСА: Баланс достаточный ${total_value:.2f} >= ${min_required:.2f}", "SAFETY")
        return True
    
    def validate_trade_amount(self, amount: float, min_amount: float = 10.0) -> bool:
        """Проверка минимальной суммы для торговли"""
        if amount < min_amount:
            log(f"❌ ПРОВЕРКА СУММЫ ТОРГОВЛИ: Сумма слишком мала ${amount:.2f} < ${min_amount:.2f}", "SAFETY")
            return False
        
        log(f"✅ ПРОВЕРКА СУММЫ ТОРГОВЛИ: Сумма достаточная ${amount:.2f} >= ${min_amount:.2f}", "SAFETY")
        return True
    
    def check_api_connection(self, client) -> bool:
        """Проверка подключения к API"""
        if not client:
            log("❌ ПРОВЕРКА ПОДКЛЮЧЕНИЯ: Клиент не инициализирован", "SAFETY")
            return False
        
        try:
            # Проверяем подключение
            client.ping()
            
            # Проверяем время сервера
            server_time = client.get_server_time()
            local_time = int(time.time() * 1000)
            time_diff = abs(server_time["serverTime"] - local_time)
            
            if time_diff > 5000:  # 5 секунд
                log(f"⚠️ ПРОВЕРКА ПОДКЛЮЧЕНИЯ: Большая разница во времени: {time_diff}мс", "SAFETY")
            
            log("✅ ПРОВЕРКА ПОДКЛЮЧЕНИЯ: API доступно", "SAFETY")
            return True
            
        except Exception as e:
            log(f"❌ ПРОВЕРКА ПОДКЛЮЧЕНИЯ: Ошибка подключения к API: {e}", "SAFETY")
            return False
    
    def perform_safety_checks(self, client=None, usdt_balance: float = 0, base_balance: float = 0, current_price: float = 0) -> List[str]:
        """Выполнение всех проверок безопасности"""
        log("🔒 НАЧАЛО ПРОВЕРОК БЕЗОПАСНОСТИ", "SAFETY")
        log("=" * 50, "SAFETY")
        
        issues = []
        
        # 1. Проверка API ключей
        if not self.validate_api_keys(self.config.api_key or "", self.config.api_secret or ""):
            issues.append("Невалидные API ключи")
        
        # 2. Проверка подключения к API (если клиент предоставлен)
        if client and not self.check_api_connection(client):
            issues.append("Нет подключения к API")
        
        # 3. Проверка разрешений аккаунта (если клиент предоставлен)
        if client and not self.check_account_permissions(client):
            issues.append("Недостаточные разрешения аккаунта")
        
        # 4. Проверка минимального баланса (если данные предоставлены)
        if current_price > 0 and not self.validate_minimum_balance(usdt_balance, base_balance, current_price):
            issues.append("Недостаточный баланс для торговли")
        
        # Итоговый результат
        if issues:
            log("❌ ПРОВЕРКИ БЕЗОПАСНОСТИ ПРОВАЛЕНЫ:", "SAFETY")
            for issue in issues:
                log(f"   - {issue}", "SAFETY")
        else:
            log("✅ ВСЕ ПРОВЕРКИ БЕЗОПАСНОСТИ ПРОЙДЕНЫ", "SAFETY")
        
        log("=" * 50, "SAFETY")
        return issues
    
    def can_perform_live_trading(self, client=None, usdt_balance: float = 0, base_balance: float = 0, current_price: float = 0) -> bool:
        """Проверка возможности выполнения реальной торговли"""
        if self.config.test_mode:
            return True  # В тестовом режиме всегда можно торговать
        
        issues = self.perform_safety_checks(client, usdt_balance, base_balance, current_price)
        return len(issues) == 0

# ========== Простая логика переключения активов ==========
class AssetSwitcher:
    """Простой класс для переключения между активами по MA сигналам"""
    
    def __init__(self, client: Optional[Client], symbol: str, trading_mode_controller: Optional['TradingModeController'] = None):
        self.client = client
        self.symbol = symbol
        self.base_asset = symbol[:-4] if symbol.endswith("USDT") else symbol.split("USDT")[0]
        self.quote_asset = "USDT"
        self.last_switch_time = 0
        self.min_switch_interval = 10  # минимум 10 секунд между переключениями
        self.trading_mode_controller = trading_mode_controller
    
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
            prefix = self.trading_mode_controller.get_trade_operation_prefix() if self.trading_mode_controller else "🧪 TEST"
            log(f"{prefix} SELL: {base_qty:.6f} {self.base_asset} -> USDT", "TEST")
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
            prefix = self.trading_mode_controller.get_trade_operation_prefix() if self.trading_mode_controller else "🧪 TEST"
            log(f"{prefix} BUY: {usdt_amount:.2f} USDT -> {qty:.6f} {self.base_asset}", "TEST")
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

# ========== Инициализация конфигурации ==========
env_config = EnvironmentConfig()

# Логируем статус конфигурации
env_config.log_configuration_status()

# Экспортируем переменные для обратной совместимости
API_KEY = env_config.api_key
API_SECRET = env_config.api_secret
SYMBOL = env_config.symbol
INTERVAL = env_config.interval
MA_SHORT = env_config.ma_short
MA_LONG = env_config.ma_long
TEST_MODE = env_config.test_mode
CHECK_INTERVAL = env_config.check_interval
STATE_PATH = env_config.state_path
MA_SPREAD_BPS = env_config.ma_spread_bps
MAX_RETRIES = env_config.max_retries
HEALTH_CHECK_INTERVAL = env_config.health_check_interval
MIN_BALANCE_USDT = env_config.min_balance_usdt

app = Flask(__name__)

# Глобальные переменные
client: Optional[Client] = None
asset_switcher: Optional[AssetSwitcher] = None
trading_mode_controller: Optional[TradingModeController] = None
safety_validator: Optional[SafetyValidator] = None
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
    global client, asset_switcher, trading_mode_controller
    
    # Создаем контроллер режима торговли
    trading_mode_controller = TradingModeController(env_config)
    trading_mode_controller.log_trading_mode_status()
    
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
            asset_switcher = AssetSwitcher(client, SYMBOL, trading_mode_controller)
            
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
        asset_switcher = AssetSwitcher(None, SYMBOL, trading_mode_controller)
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
    "30m": Client.KLINE_INTERVAL_30MINUTE,
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

@app.route("/config-status")
def config_status():
    """Подробная диагностика конфигурации и переменных окружения"""
    
    # Проверяем источники переменных окружения
    env_sources = {}
    critical_vars = ["TEST_MODE", "BINANCE_API_KEY", "BINANCE_API_SECRET", "SYMBOL"]
    
    for var in critical_vars:
        system_value = os.environ.get(var)
        dotenv_value = os.getenv(var)
        
        if system_value is not None:
            source = "системные переменные окружения"
            value = system_value
        elif dotenv_value is not None:
            source = ".env файл"
            value = dotenv_value
        else:
            source = "значение по умолчанию"
            value = "не установлено"
        
        # Маскируем API ключи для безопасности
        if "API" in var and value != "не установлено":
            display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "установлен"
        else:
            display_value = value
            
        env_sources[var] = {
            "value": display_value,
            "source": source,
            "is_set": value != "не установлено"
        }
    
    # Статус конфигурации
    config_issues = []
    if not env_config.config_status.api_keys_present:
        config_issues.append("API ключи не настроены")
    if env_config.config_status.test_mode and env_sources["TEST_MODE"]["source"] == "значение по умолчанию":
        config_issues.append("TEST_MODE использует небезопасное значение по умолчанию")
    
    return jsonify({
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trading_mode": {
            "current": "TEST" if TEST_MODE else "LIVE",
            "test_mode_value": TEST_MODE,
            "source": env_sources["TEST_MODE"]["source"],
            "warning": "Используется тестовый режим" if TEST_MODE else "ВНИМАНИЕ: Реальная торговля активна!"
        },
        "environment_variables": env_sources,
        "configuration_status": {
            "api_keys_present": env_config.config_status.api_keys_present,
            "safety_checks_passed": env_config.config_status.safety_checks_passed,
            "issues": config_issues
        },
        "file_status": {
            "env_file_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'),
            "env_file_exists": os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
        },
        "recommendations": [
            "Для реального режима установите TEST_MODE=false в переменных окружения Render",
            "Убедитесь что API ключи настроены корректно",
            "Проверьте права API ключей в Binance (только спот-торговля)",
            "Мониторьте логи после переключения режима"
        ] if TEST_MODE else [
            "Бот работает в реальном режиме - мониторьте операции",
            "Проверяйте баланс и результаты торговли",
            "Убедитесь что стратегия работает корректно"
        ]
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
    