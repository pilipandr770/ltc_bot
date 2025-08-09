# Design Document

## Overview

Дизайн улучшений для торгового бота направлен на устранение критических проблем с OCO ордерами, синхронизацией состояния и обработкой ошибок. Архитектура будет расширена новыми компонентами для мониторинга ордеров, управления рисками и автоматического восстановления.

## Architecture

### Текущая архитектура
```
Flask App
├── Trading Loop (основной цикл)
├── State Management (управление состоянием)
├── Binance Client (API клиент)
├── Signal Detection (обнаружение сигналов)
└── Order Management (управление ордерами)
```

### Новая улучшенная архитектура
```
Flask App
├── Trading Engine
│   ├── Trading Loop (основной цикл)
│   ├── Signal Detection (обнаружение сигналов)
│   └── Risk Manager (управление рисками)
├── Order Management System
│   ├── Order Tracker (отслеживание ордеров)
│   ├── OCO Monitor (мониторинг OCO)
│   └── Order Cleanup (очистка ордеров)
├── State Synchronization
│   ├── Balance Reconciler (сверка балансов)
│   ├── Position Validator (валидация позиций)
│   └── State Persistence (сохранение состояния)
├── Error Recovery System
│   ├── Circuit Breaker (автоматический выключатель)
│   ├── Retry Manager (управление повторами)
│   └── Safe Mode (безопасный режим)
└── Monitoring & Alerting
    ├── Performance Metrics (метрики производительности)
    ├── Health Checker (проверка здоровья)
    └── Alert System (система уведомлений)
```

## Components and Interfaces

### 1. Order Management System

#### OrderTracker Class
```python
class OrderTracker:
    def __init__(self):
        self.active_orders: Dict[str, Dict] = {}
        self.oco_orders: Dict[str, Dict] = {}
    
    def add_order(self, order_id: str, order_data: Dict)
    def remove_order(self, order_id: str)
    def get_order_status(self, order_id: str) -> str
    def cleanup_old_orders(self, max_age_hours: int = 24)
```

#### OCOMonitor Class
```python
class OCOMonitor:
    def __init__(self, client: Client):
        self.client = client
        self.tracked_oco: Dict[str, Dict] = {}
    
    def track_oco_order(self, oco_id: str, position_data: Dict)
    def check_oco_status(self) -> List[Dict]
    def handle_oco_execution(self, oco_id: str, execution_data: Dict)
```

### 2. State Synchronization System

#### BalanceReconciler Class
```python
class BalanceReconciler:
    def __init__(self, client: Client):
        self.client = client
    
    def get_real_balances(self) -> Tuple[float, float]
    def compare_with_saved_state(self, saved_state: Dict) -> Dict
    def reconcile_position(self, real_balances: Tuple, saved_state: Dict) -> Dict
```

#### PositionValidator Class
```python
class PositionValidator:
    def __init__(self, symbol: str, min_position_value: float):
        self.symbol = symbol
        self.min_position_value = min_position_value
    
    def validate_position(self, position: str, qty: float, price: float) -> bool
    def suggest_correction(self, current_state: Dict, real_balances: Tuple) -> Dict
```

### 3. Risk Management System

#### RiskManager Class
```python
class RiskManager:
    def __init__(self, config: Dict):
        self.config = config
        self.volatility_tracker = VolatilityTracker()
        self.drawdown_tracker = DrawdownTracker()
    
    def calculate_position_size(self, balance: float, volatility: float) -> float
    def check_market_conditions(self, prices: List[float]) -> Dict
    def should_pause_trading(self) -> bool
    def adjust_risk_parameters(self, market_conditions: Dict) -> Dict
```

#### VolatilityTracker Class
```python
class VolatilityTracker:
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.price_history: List[float] = []
    
    def update_prices(self, new_price: float)
    def calculate_volatility(self) -> float
    def is_high_volatility(self, threshold: float = 0.05) -> bool
```

### 4. Error Recovery System

#### CircuitBreaker Class
```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs)
    def record_success(self)
    def record_failure(self)
    def is_open(self) -> bool
```

#### SafeMode Class
```python
class SafeMode:
    def __init__(self):
        self.is_active = False
        self.activation_reason = ""
        self.activation_time = None
    
    def activate(self, reason: str)
    def deactivate(self)
    def should_allow_trading(self) -> bool
    def get_safe_mode_status(self) -> Dict
```

## Data Models

### Enhanced Bot Status
```python
bot_status = {
    # Основные поля (существующие)
    "status": str,
    "symbol": str,
    "position": str,
    "qty": float,
    "avg_price": float,
    
    # Новые поля для улучшенного мониторинга
    "active_orders": Dict[str, Dict],
    "oco_orders": Dict[str, Dict],
    "last_order_check": str,
    "position_validated": bool,
    "balance_synced": bool,
    "risk_level": str,  # "LOW", "MEDIUM", "HIGH"
    "volatility": float,
    "drawdown": float,
    "safe_mode": bool,
    "circuit_breaker_state": str,
    
    # Метрики производительности
    "total_trades": int,
    "successful_trades": int,
    "failed_trades": int,
    "total_pnl": float,
    "max_drawdown": float,
    "sharpe_ratio": float,
    
    # Системные метрики
    "api_calls_count": int,
    "api_errors_count": int,
    "last_api_error": str,
    "memory_usage": float,
    "cpu_usage": float
}
```

### Order Tracking Model
```python
order_data = {
    "order_id": str,
    "type": str,  # "MARKET", "LIMIT", "OCO"
    "side": str,  # "BUY", "SELL"
    "symbol": str,
    "quantity": float,
    "price": float,
    "status": str,  # "NEW", "FILLED", "CANCELED", "EXPIRED"
    "created_time": str,
    "updated_time": str,
    "fills": List[Dict],
    "related_position": str  # связанная позиция
}
```

## Error Handling

### Иерархия обработки ошибок
1. **Уровень функции**: retry_on_error с экспоненциальной задержкой
2. **Уровень компонента**: Circuit Breaker для критических компонентов
3. **Уровень системы**: Safe Mode при критических сбоях
4. **Уровень восстановления**: Автоматическая синхронизация состояния

### Типы ошибок и стратегии
- **API Rate Limit**: Экспоненциальная задержка + Circuit Breaker
- **Network Errors**: Повторные попытки + переключение на Safe Mode
- **Order Errors**: Логирование + очистка некорректных ордеров
- **State Inconsistency**: Автоматическая синхронизация с реальными балансами

## Testing Strategy

### Unit Tests
- Тестирование каждого компонента изолированно
- Мокирование Binance API для тестирования логики
- Тестирование граничных случаев и ошибок

### Integration Tests
- Тестирование взаимодействия компонентов
- Тестирование полного цикла торговли
- Тестирование восстановления после ошибок

### Performance Tests
- Нагрузочное тестирование API вызовов
- Тестирование производительности при высокой волатильности
- Тестирование утечек памяти при длительной работе

### End-to-End Tests
- Тестирование в тестовой среде Binance
- Симуляция различных рыночных условий
- Тестирование аварийных сценариев

## Implementation Phases

### Phase 1: Order Management System
- Реализация OrderTracker и OCOMonitor
- Интеграция с существующим кодом
- Добавление отслеживания OCO ордеров

### Phase 2: State Synchronization
- Реализация BalanceReconciler и PositionValidator
- Автоматическая синхронизация при запуске
- Периодическая проверка консистентности

### Phase 3: Risk Management
- Реализация RiskManager и VolatilityTracker
- Динамическое управление размером позиции
- Защита от экстремальных рыночных условий

### Phase 4: Error Recovery
- Реализация CircuitBreaker и SafeMode
- Автоматическое восстановление после сбоев
- Улучшенное логирование и мониторинг

### Phase 5: Monitoring & Optimization
- Добавление метрик производительности
- Система алертов и уведомлений
- Оптимизация производительности

## Security Considerations

- Безопасное хранение API ключей
- Валидация всех входящих данных
- Ограничение размера позиций и рисков
- Логирование всех критических операций
- Защита от несанкционированного доступа к API эндпоинтам

## Scalability

- Модульная архитектура для легкого расширения
- Возможность добавления новых торговых стратегий
- Поддержка множественных торговых пар
- Горизонтальное масштабирование через микросервисы