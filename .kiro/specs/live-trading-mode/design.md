# Design Document

## Overview

Проблема заключается в том, что торговый бот работает в тестовом режиме несмотря на настройку `TEST_MODE=false` в конфигурации. Анализ показал, что:

1. В `app/.env` установлено `TEST_MODE=false`
2. В `render.yaml` также установлено `TEST_MODE=false`
3. Но в коде по умолчанию `TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"`
4. В логах видно `TEST_MODE=True` и выполняются тестовые операции

Основная проблема: переменные окружения в Render не установлены или не загружаются корректно, поэтому используется значение по умолчанию `"true"`.

## Architecture

### Компоненты системы

1. **Environment Configuration Manager** - управление загрузкой и валидацией переменных окружения
2. **Trading Mode Controller** - контроль режима торговли и переключения между тестовым/реальным режимом
3. **Safety Validator** - проверки безопасности при переходе в реальный режим
4. **Configuration Diagnostics** - диагностика и отладка конфигурации

### Приоритет загрузки переменных окружения

1. **Системные переменные окружения** (Render, Docker) - высший приоритет
2. **Локальный .env файл** - средний приоритет
3. **Значения по умолчанию в коде** - низший приоритет

## Components and Interfaces

### Environment Configuration Manager

```python
class EnvironmentConfig:
    def __init__(self):
        self.load_environment()
        self.validate_configuration()
    
    def load_environment(self):
        """Загрузка переменных окружения с правильным приоритетом"""
        
    def validate_configuration(self):
        """Валидация критических настроек"""
        
    def get_trading_mode(self) -> bool:
        """Определение режима торговли с диагностикой"""
        
    def log_configuration_status(self):
        """Подробное логирование текущей конфигурации"""
```

### Trading Mode Controller

```python
class TradingModeController:
    def __init__(self, config: EnvironmentConfig):
        self.config = config
        self.test_mode = config.get_trading_mode()
    
    def is_test_mode(self) -> bool:
        """Проверка текущего режима торговли"""
        
    def switch_to_live_mode(self):
        """Переключение в реальный режим с проверками"""
        
    def validate_live_mode_requirements(self) -> bool:
        """Проверка требований для реального режима"""
```

### Safety Validator

```python
class SafetyValidator:
    def validate_api_keys(self, api_key: str, api_secret: str) -> bool:
        """Проверка валидности API ключей"""
        
    def check_account_permissions(self, client) -> bool:
        """Проверка разрешений аккаунта для торговли"""
        
    def validate_minimum_balance(self, balance: float) -> bool:
        """Проверка минимального баланса"""
        
    def perform_safety_checks(self) -> List[str]:
        """Выполнение всех проверок безопасности"""
```

## Data Models

### Configuration Status

```python
@dataclass
class ConfigurationStatus:
    test_mode: bool
    api_keys_present: bool
    api_keys_valid: bool
    environment_source: str  # "system", "file", "default"
    configuration_issues: List[str]
    safety_checks_passed: bool
```

### Trading Mode Status

```python
@dataclass
class TradingModeStatus:
    current_mode: str  # "TEST" or "LIVE"
    mode_source: str   # откуда взято значение
    can_switch_to_live: bool
    blocking_issues: List[str]
    last_mode_change: Optional[datetime]
```

## Error Handling

### Configuration Errors

1. **Missing Environment Variables**
   - Логирование отсутствующих переменных
   - Использование безопасных значений по умолчанию
   - Предупреждения пользователю

2. **Invalid API Keys**
   - Проверка формата ключей
   - Тестирование подключения к API
   - Блокировка реального режима при невалидных ключах

3. **Conflicting Configuration**
   - Приоритизация системных переменных
   - Логирование конфликтов
   - Четкое указание используемых значений

### Runtime Errors

1. **API Connection Failures**
   - Автоматический откат в тестовый режим
   - Повторные попытки подключения
   - Детальное логирование ошибок

2. **Insufficient Balance**
   - Предупреждения о недостаточном балансе
   - Остановка торговли при критически низком балансе
   - Рекомендации по пополнению

## Testing Strategy

### Unit Tests

1. **Environment Configuration Tests**
   - Тестирование загрузки переменных из разных источников
   - Проверка приоритетов конфигурации
   - Валидация значений по умолчанию

2. **Trading Mode Controller Tests**
   - Тестирование переключения режимов
   - Проверка блокировок при невалидной конфигурации
   - Тестирование проверок безопасности

3. **Safety Validator Tests**
   - Тестирование валидации API ключей
   - Проверка минимальных балансов
   - Тестирование разрешений аккаунта

### Integration Tests

1. **End-to-End Configuration Tests**
   - Тестирование полного цикла загрузки конфигурации
   - Проверка работы в разных средах (локальная, продакшн)
   - Тестирование переключения режимов

2. **API Integration Tests**
   - Тестирование подключения к Binance API
   - Проверка торговых операций в тестовом режиме
   - Валидация реальных API вызовов (с минимальными суммами)

### Manual Testing

1. **Configuration Verification**
   - Проверка переменных окружения в Render
   - Тестирование локальной конфигурации
   - Верификация логов конфигурации

2. **Mode Switching Tests**
   - Ручное переключение между режимами
   - Проверка поведения при разных конфигурациях
   - Тестирование предупреждений и блокировок

## Implementation Notes

### Immediate Fixes

1. **Render Environment Variables**
   - Проверить и установить переменные окружения в веб-интерфейсе Render
   - Убедиться что `TEST_MODE=false` установлено корректно
   - Перезапустить сервис после изменения переменных

2. **Configuration Diagnostics**
   - Добавить подробное логирование загрузки переменных окружения
   - Показывать источник каждой переменной (система/файл/по умолчанию)
   - Логировать все критические настройки при запуске

3. **Safety Improvements**
   - Изменить значение по умолчанию для `TEST_MODE` на более безопасное
   - Добавить дополнительные проверки перед реальной торговлей
   - Улучшить предупреждения о режиме торговли

### Long-term Improvements

1. **Configuration Management**
   - Создать централизованный класс для управления конфигурацией
   - Добавить валидацию всех критических параметров
   - Реализовать горячую перезагрузку конфигурации

2. **Monitoring and Alerting**
   - Добавить мониторинг режима торговли
   - Настроить алерты при переключении режимов
   - Создать дашборд для отслеживания статуса бота