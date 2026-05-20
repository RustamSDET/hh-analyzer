import sys
import os

# Добавляем текущую директорию в пути поиска Python модулей
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    print("🤖 [TEST] Запуск экспресс-теста Vertex AI...")
    from src.analyzer.llm_factory import get_vertex_llm
    
    # Инициализируем модель по единому конфигу
    llm = get_vertex_llm()
    
    print("📡 [TEST] Отправка тестового запроса (пинг)...")
    response = llm.invoke("Привет! Ответь одним словом 'Работает', если ты меня слышишь.")
    
    print("\n🎉 === РЕЗУЛЬТАТ ТЕСТА ===")
    print(f"Ответ от Gemini Вертекса: {response.content}")
    print("==========================\n")

except Exception as e:
    print("\n❌ === ТЕСТ ПОВАЛЕН! ОШИБКА ПОДКЛЮЧЕНИЯ ===")
    print(f"Тип ошибки: {type(e).__name__}")
    print(f"Детали ошибки: {e}")
    print("==========================================\n")