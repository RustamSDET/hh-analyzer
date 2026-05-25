import os
import json
import logging
from src.parser import HHWebClient
from src.database import DBManager
from src.analyzer import run_vacancy_analysis, run_vacancy_analysis_batch

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
    import random
    import time
    
    vacancies_to_parse = db.get_vacancies_for_parsing()
    print(f"[MAIN] Найдено в БД вакансий, требующих парсинга деталей: {len(vacancies_to_parse)}")
 
    for idx, v in enumerate(vacancies_to_parse):
        v_id = v["id"]
        print(f"[MAIN] Обработка {idx+1}/{len(vacancies_to_parse)}: Скачиваем детали для ID {v_id}")
        
        if idx > 0:
            delay = random.uniform(2.0, 5.0)
            print(f"[MAIN] Пауза {delay:.2f} сек. для предотвращения бана...")
            time.sleep(delay)
            
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
    # Берем PARSED + FAILED, но только те, у которых есть непустое описание (чтобы не анализировать пустые вакансии)
    all_candidates = db.get_vacancies_by_status("PARSED") + db.get_vacancies_by_status("FAILED")
    parsed_vacancies = [v for v in all_candidates if v.get("description") and v["description"].strip()]
    print(f"[MAIN] Вакансий, готовых к ИИ-анализу: {len(parsed_vacancies)}")

    if parsed_vacancies:
        # Запускаем пакетный анализ (по 10 штук за раз)
        batch_results = run_vacancy_analysis_batch(
            my_profile=my_profile_text, 
            vacancies_data=parsed_vacancies, 
            batch_size=10
        )
        
        for v, ai_result in batch_results:
            v_id = v["id"]
            if ai_result is None:
                print(f"[MAIN] ❌ Пропуск или ошибка анализа ИИ для ID {v_id}. Помечаем как FAILED.")
                db.mark_as_failed(v_id)
                continue
                
            try:
                details_dict = {
                    "pros": ai_result.pros,
                    "cons": ai_result.cons,
                    "red_flags": ai_result.red_flags,
                    "summary": ai_result.summary,
                    "ip_analysis_reason": ai_result.ip_analysis_reason,
                    "ip_cooperation_chance": ai_result.ip_cooperation_chance,
                    "grade_score": ai_result.grade_score,
                    "remote_chance": ai_result.remote_chance,
                    "stack_score": ai_result.stack_score
                }
                
                print(f"[MAIN] Сохранение вердикта ИИ (Оценка: {ai_result.score}) в БД для {v['name']}...")
                db.update_ai_analysis(
                    v_id, 
                    ai_result.score, 
                    ai_result.grade_score, 
                    ai_result.remote_chance, 
                    ai_result.stack_score, 
                    json.dumps(details_dict, ensure_ascii=False)
                )
                print(f"[MAIN] ✅ Вакансия {v_id} успешно проанализирована.")
            except Exception as e:
                print(f"[MAIN] ❌ Ошибка сохранения вердикта ИИ для ID {v_id}: {e}")
                db.mark_as_failed(v_id)

    print("\n[MAIN] 🎉 Работа пайплайна main.py ПОЛНОСТЬЮ ЗАВЕРШЕНА!")

if __name__ == "__main__":
    main()