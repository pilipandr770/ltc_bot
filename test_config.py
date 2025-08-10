#!/usr/bin/env python3
"""
Тестовый скрипт для диагностики загрузки переменных окружения
"""
import os
import sys
sys.path.insert(0, 'app')

from dotenv import load_dotenv

def test_environment_loading():
    print("🔍 ДИАГНОСТИКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ")
    print("=" * 60)
    
    # Проверяем системные переменные окружения
    print("📋 СИСТЕМНЫЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
    system_test_mode = os.environ.get("TEST_MODE")
    system_api_key = os.environ.get("BINANCE_API_KEY")
    print(f"   TEST_MODE (система): {system_test_mode}")
    print(f"   BINANCE_API_KEY (система): {'установлен' if system_api_key else 'не установлен'}")
    
    # Загружаем .env файл
    print("\n📁 ЗАГРУЗКА .env ФАЙЛА:")
    print("   Проверяем app/.env файл...")
    if os.path.exists("app/.env"):
        print("   ✅ app/.env файл найден")
        load_dotenv("app/.env")
    else:
        print("   ❌ app/.env файл не найден")
        load_dotenv()  # Загружаем из текущей директории
    
    # Проверяем переменные после загрузки .env
    print("📋 ПЕРЕМЕННЫЕ ПОСЛЕ ЗАГРУЗКИ .env:")
    dotenv_test_mode = os.getenv("TEST_MODE")
    dotenv_api_key = os.getenv("BINANCE_API_KEY")
    print(f"   TEST_MODE (после .env): {dotenv_test_mode}")
    print(f"   BINANCE_API_KEY (после .env): {'установлен' if dotenv_api_key else 'не установлен'}")
    
    # Проверяем приоритет
    print("\n🎯 АНАЛИЗ ПРИОРИТЕТА:")
    if system_test_mode is not None:
        print(f"   TEST_MODE будет взят из системных переменных: {system_test_mode}")
    elif dotenv_test_mode is not None:
        print(f"   TEST_MODE будет взят из .env файла: {dotenv_test_mode}")
    else:
        print("   TEST_MODE будет использовать значение по умолчанию: true")
    
    # Финальное значение
    final_test_mode = os.getenv("TEST_MODE", "true").lower() == "true"
    print(f"\n✅ ФИНАЛЬНОЕ ЗНАЧЕНИЕ TEST_MODE: {final_test_mode}")
    print(f"   Режим торговли: {'ТЕСТОВЫЙ' if final_test_mode else 'РЕАЛЬНЫЙ'}")
    
    print("=" * 60)

if __name__ == "__main__":
    test_environment_loading()