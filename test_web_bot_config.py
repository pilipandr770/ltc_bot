#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки конфигурации в web_bot.py
"""
import sys
sys.path.insert(0, 'app')

# Импортируем только класс EnvironmentConfig, чтобы не запускать весь бот
from web_bot import EnvironmentConfig

def test_web_bot_config():
    print("🔍 ТЕСТИРОВАНИЕ КОНФИГУРАЦИИ WEB_BOT")
    print("=" * 60)
    
    # Создаем экземпляр конфигурации
    config = EnvironmentConfig()
    
    print(f"\n✅ РЕЗУЛЬТАТЫ ЗАГРУЗКИ:")
    print(f"   TEST_MODE: {config.test_mode}")
    print(f"   API_KEY присутствует: {bool(config.api_key)}")
    print(f"   SYMBOL: {config.symbol}")
    
    print("=" * 60)

if __name__ == "__main__":
    test_web_bot_config()