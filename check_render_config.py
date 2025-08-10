#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации бота в Render
"""
import requests
import json
from datetime import datetime

def check_render_config(url="https://ltc-bot-1.onrender.com"):
    """Проверка конфигурации бота через API"""
    
    print("🔍 ПРОВЕРКА КОНФИГУРАЦИИ БОТА В RENDER")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Время проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Проверяем основной статус
        print("📊 ОСНОВНОЙ СТАТУС:")
        response = requests.get(f"{url}/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            mode = "🔴 РЕАЛЬНЫЙ" if not status.get("mode") == "TEST" else "🧪 ТЕСТОВЫЙ"
            print(f"   Режим торговли: {mode}")
            print(f"   Статус: {status.get('status', 'неизвестно')}")
            print(f"   Символ: {status.get('symbol', 'неизвестно')}")
            print(f"   Время работы: {status.get('uptime', 0)} сек")
        else:
            print(f"   ❌ Ошибка получения статуса: {response.status_code}")
        
        print()
        
        # Проверяем детальную конфигурацию
        print("🔧 ДЕТАЛЬНАЯ КОНФИГУРАЦИЯ:")
        response = requests.get(f"{url}/config-status", timeout=10)
        if response.status_code == 200:
            config = response.json()
            
            # Режим торговли
            trading_mode = config.get("trading_mode", {})
            current_mode = trading_mode.get("current", "неизвестно")
            source = trading_mode.get("source", "неизвестно")
            warning = trading_mode.get("warning", "")
            
            print(f"   Текущий режим: {current_mode}")
            print(f"   Источник TEST_MODE: {source}")
            print(f"   Предупреждение: {warning}")
            print()
            
            # Переменные окружения
            print("📋 ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
            env_vars = config.get("environment_variables", {})
            for var, info in env_vars.items():
                status_icon = "✅" if info.get("is_set") else "❌"
                print(f"   {status_icon} {var}: {info.get('value')} (источник: {info.get('source')})")
            print()
            
            # Проблемы конфигурации
            config_status = config.get("configuration_status", {})
            issues = config_status.get("issues", [])
            if issues:
                print("⚠️ ПРОБЛЕМЫ КОНФИГУРАЦИИ:")
                for issue in issues:
                    print(f"   - {issue}")
            else:
                print("✅ ПРОБЛЕМ КОНФИГУРАЦИИ НЕ ОБНАРУЖЕНО")
            print()
            
            # Рекомендации
            recommendations = config.get("recommendations", [])
            if recommendations:
                print("💡 РЕКОМЕНДАЦИИ:")
                for rec in recommendations:
                    print(f"   - {rec}")
        else:
            print(f"   ❌ Ошибка получения детальной конфигурации: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка подключения к боту: {e}")
        print("   Возможные причины:")
        print("   - Бот не запущен")
        print("   - Неправильный URL")
        print("   - Проблемы с сетью")
    
    print("=" * 60)

if __name__ == "__main__":
    # Можно указать свой URL
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://ltc-bot-1.onrender.com"
    check_render_config(url)