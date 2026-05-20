import os
import json
import logging
from src.parser import HHWebClient
from src.database import DBManager
from src.analyzer import run_vacancy_analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    print("\n[MAIN] >>> ЗАПУСК С КРИПТА MAIN.PY <<<")
    db = DBManager()
    client = HHWebClient()
    
    profile_path = "my_profile.txt"
    if not os.path.exists(profile_path):
        print(f"[MAIN] ❌ КРИТИЧЕСКАЯ ОШИБКА: Файл профиля {profile_path} не найден!")
        return
        
    with open(profile_path, "r", encoding="utf-8") as f:
        my_profile_text = f.read()
    print(f"[MAIN] Профиль успешно загружен. Размер текста: {len(my_profile_text)} симв.")

    # ========================================================
    # ФАЗА 1: Сбор новых вакансий (Глобальный поиск)
    # ========================================================
    print("\n[MAIN] === ЗАПУСК ФАЗЫ 1: Глобальный поиск ===")
    try:
        search_page = client.fetch_vacancies_page(page=0)
        search_result = search_page.get("vacancySearchResult", {})
        found_items = search_result.get("vacancies", [])
        
        db.save_discovered_vacancies(found_items)
        print(f"[MAIN] Фаза 1 успешно завершена. Обработано вакансий в выдаче: {len(found_items)}")
    except Exception as e:
        print(f"[MAIN] 💥 Ошибка во время глобального поиска: {e}")

    # ========================================================
    # ФАЗА 2: Скачивание описаний
    # ========================================================
    print("\n[MAIN] === ЗАПУСК ФАЗЫ 2: Детальный парсинг HTML ===")
    new_vacancies = db.get_vacancies_by_status("NEW")
    print(f"[MAIN] Найдено в БД вакансий в статусе NEW: {len(new_vacancies)}")

    for idx, v in enumerate(new_vacancies):
        v_id = v["id"]
        print(f"[MAIN] Обработка {idx+1}/{len(new_vacancies)}: Скачиваем детали для ID {v_id}")
        try:
            raw_details = client.fetch_vacancy_details(v_id)
            db.update_vacancy_details(
                vacancy_id=v_id,
                description=raw_details.get("description", ""),
                key_skills=raw_details.get("key_skills", [])
            )
            print(f"[MAIN] -> Успешно скачана и сохранена карточка ID {v_id}")
        except Exception as e:
            print(f"[MAIN] ❌ Не удалось обработать вакансию ID {v_id}: {e}")
            db.mark_as_failed(v_id)

    # ========================================================
    # ФАЗА 3: ИИ-Анализ
    # ========================================================
    print("\n[MAIN] === ЗАПУСК ФАЗЫ 3: ИИ-Скрининг ===")
    # 🟢 ИСПРАВЛЕНИЕ: Тоже берем PARSED + FAILED
    parsed_vacancies = db.get_vacancies_by_status("PARSED") + db.get_vacancies_by_status("FAILED")
    print(f"[MAIN] Вакансий, готовых к ИИ-анализу: {len(parsed_vacancies)}")

    for v in parsed_vacancies:
        v_id = v["id"]
        print(f"[MAIN] Отправка в Gemini: {v['name']} в компании {v['employer_name']}")
        try:
            ai_result = run_vacancy_analysis(my_profile=my_profile_text, vacancy_data=v)
            
            details_dict = {
                "pros": ai_result.pros,
                "cons": ai_result.cons,
                "red_flags": ai_result.red_flags,
                "summary": ai_result.summary,
                "ip_analysis_reason": ai_result.ip_analysis_reason,
                "ip_cooperation_chance": ai_result.ip_cooperation_chance
            }
            
            print(f"[MAIN] Сохранение вердикта ИИ (Оценка: {ai_result.score}) в БД...")
            db.update_ai_analysis(v_id, ai_result.score, json.dumps(details_dict, ensure_ascii=False))
            print(f"[MAIN] ✅ Вакансия {v_id} успешно проанализирована.")
        except Exception as e:
            print(f"[MAIN] ❌ Ошибка анализа ИИ для ID {v_id}: {e}")
            db.mark_as_failed(v_id)

    print("\n[MAIN] 🎉 Работа пайплайна main.py ПОЛНОСТЬЮ ЗАВЕРШЕНА!")

if __name__ == "__main__":
    main()