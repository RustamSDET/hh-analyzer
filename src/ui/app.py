import streamlit as st
import os
import sys
import json

# Находим путь к корню проекта (на два уровня выше, чем текущий app.py)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database import DBManager
from src.parser import HHWebClient  # Оставили только нужный веб-клиент
from src.analyzer import run_vacancy_analysis
from src.ui.components import render_vacancy_card

# Настройка страницы (должна быть первой командой Streamlit)
st.set_page_config(page_title="QA Job AI Analyzer", page_icon="🕵️‍♂️", layout="wide")

db = DBManager()

# Чтение профиля (резюме)
PROFILE_PATH = "my_profile.txt"
my_profile_text = ""
if os.path.exists(PROFILE_PATH):
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        my_profile_text = f.read()

# ==========================================
# SIDEBAR: Управление и Статистика
# ==========================================
st.sidebar.title("🧠 Управление ИИ-Хантером")

st.sidebar.subheader("📊 Статистика базы")
total_new = len(db.get_vacancies_by_status("NEW"))
total_parsed = len(db.get_vacancies_by_status("PARSED"))
total_analyzed = len(db.get_vacancies_by_status("ANALYZED"))

st.sidebar.text(f"Новые (только ID): {total_new}")
st.sidebar.text(f"Спарсенные (ожидают ИИ): {total_parsed}")
st.sidebar.text(f"Проанализированные: {total_analyzed}")
st.sidebar.markdown("---")

st.sidebar.subheader("⚙️ Запуск процессов")

# --- КНОПКА 1: СБОР ВАКАНСИЙ ---
if st.sidebar.button("🔄 1. Собрать вакансии за 24ч", use_container_width=True):
    print("\n==================================================")
    print("[UI BUTTON] Нажата кнопка '1. Собрать вакансии за 24ч'")
    print("==================================================")
    
    with st.spinner("Запрос к HH.ru и скачивание деталей..."):
        log_area = st.sidebar.empty()
        client = HHWebClient()
        
        # --- ФАЗА 1: ПОИСК ---
        print("[UI PATH] >>> Запуск Фазы 1 (Поиск и сбор метаданных) внутри UI...")
        log_area.caption("Поиск свежих вакансий...")
        try:
            search_page = client.fetch_vacancies_page(page=0)
            print("[UI PATH] Фаза 1: Сетевой ответ получен успешно. Разбираем структуру...")
            
            search_result = search_page.get("vacancySearchResult", {})
            found_items = search_result.get("vacancies", [])
            
            print(f"[UI PATH] Фаза 1: Извлечено {len(found_items)} вакансий. Передаем в БД для массовой вставки...")
            # Сохраняем объекты целиком, чтобы не потерять имена компаний и названия позиций
            db.save_discovered_vacancies(found_items)
            print("[UI PATH] Фаза 1: Первичные данные успешно записаны в SQLite.")
        except Exception as e:
            print(f"[UI PATH] 💥 Ошибка на Фазе 1: {e}")
            st.sidebar.error(f"Ошибка поиска: {e}")
            
        # --- ФАЗА 2: ДЕТАЛИЗАЦИЯ (HTML) ---
        print("\n[UI PATH] >>> Переход к Фазе 2 (Скачивание HTML-описаний и навыков)...")
        new_vacancies = db.get_vacancies_by_status("NEW")
        print(f"[UI PATH] Из базы извлечено {len(new_vacancies)} вакансий в статусе NEW для докачки HTML.")
        
        for idx, v in enumerate(new_vacancies):
            v_id = v["id"]
            print(f"[UI PATH] Цикл Фазы 2: Обработка {idx+1}/{len(new_vacancies)} (ID: {v_id})")
            log_area.caption(f"Парсинг {idx+1}/{len(new_vacancies)}: ID {v_id}")
            try:
                raw_details = client.fetch_vacancy_details(v_id)
                print(f"[UI PATH] HTML страницы ID {v_id} успешно скачан и очищен от тегов.")
                
                print(f"[UI PATH] Обновляем описание и навыки в БД (статус -> 'PARSED') для ID: {v_id}")
                # Обновляем точечно, сохраняя имя и компанию, полученные на Шаге 1
                db.update_vacancy_details(
                    vacancy_id=v_id,
                    description=raw_details.get("description", ""),
                    key_skills=raw_details.get("key_skills", [])
                )
                print(f"[UI PATH] -> Вакансия ID {v_id} успешно переведена в статус PARSED.")
            except Exception as e:
                print(f"[UI PATH] ❌ Ошибка скачивания HTML-карточки ID {v_id}: {e}")
                db.mark_as_failed(v_id)
        
        print("[UI PATH] 🎉 ВСЕ ФАЗЫ ПАРСИНГА УСПЕШНО ВЫПОЛНЕНЫ БЕЗ ОШИБОК 406!")
        st.sidebar.success("Сбор данных успешно завершен!")
        st.rerun()

# --- КНОПКА 2: ИИ-СКРИНИНГ ---
if st.sidebar.button("🤖 2. Запустить ИИ-скрининг", use_container_width=True):
    print("\n==================================================")
    print("[UI BUTTON] Нажата кнопка '2. Запустить ИИ-скрининг'")
    print("==================================================")
    if not my_profile_text:
        st.sidebar.error("Сначала создайте файл my_profile.txt в корне!")
    else:
        parsed_vacancies = db.get_vacancies_by_status("PARSED")
        print(f"[UI PATH] Найдено {len(parsed_vacancies)} вакансий для ИИ-анализа (в статусе PARSED).")
        
        if not parsed_vacancies:
            st.sidebar.info("Нет вакансий для анализа ИИ. Сначала запустите сбор.")
        else:
            progress_bar = st.sidebar.progress(0.0)
            log_area = st.sidebar.empty()
            
            for idx, v in enumerate(parsed_vacancies):
                print(f"[UI PATH] ИИ-Анализ {idx+1}/{len(parsed_vacancies)}: {v['name']} ({v['employer_name']})")
                log_area.caption(f"Анализ {idx+1}/{len(parsed_vacancies)}: {v['name']}")
                try:
                    # Запуск аналитического графа Gemini 3.5 Flash
                    ai_result = run_vacancy_analysis(my_profile=my_profile_text, vacancy_data=v)
                    
                    details_dict = {
                        "pros": ai_result.pros,
                        "cons": ai_result.cons,
                        "red_flags": ai_result.red_flags,
                        "summary": ai_result.summary,
                        "ip_analysis_reason": ai_result.ip_analysis_reason,
                        "ip_cooperation_chance": ai_result.ip_cooperation_chance
                    }
                    
                    print(f"[UI PATH] Сохраняем вердикт ИИ в БД (Оценка: {ai_result.score}/5, ИП: {ai_result.ip_cooperation_chance})")
                    db.update_ai_analysis(v["id"], ai_result.score, json.dumps(details_dict, ensure_ascii=False))
                    print(f"[UI PATH] -> Данные вакансии ID {v['id']} успешно обновлены.")
                except Exception as e:
                    print(f"[UI PATH] ❌ Ошибка выполнения ИИ-модели для ID {v['id']}: {e}")
                    db.mark_as_failed(v["id"])
                    
                progress_bar.progress((idx + 1) / len(parsed_vacancies))
                
            print("[UI PATH] 🎉 ИИ-АНАЛИЗ ВСЕГО ПАКЕТА ВАКАНСИЙ С ЗАВЕРШЕН!")
            st.sidebar.success("ИИ-анализ успешно завершен!")
            st.rerun()

# ==========================================
# ГЛАВНЫЙ ЭКРАН: Отображение результатов
# ==========================================
st.title("🕵️‍♂️ Персональный ИИ-Скрининг Вакансий")
tab1, tab2, tab3 = st.tabs(["🔥 Топ Матчи (Оценка 4-5)", "📂 Все проанализированные", "📄 Твое Резюме"])

with tab1:
    st.subheader("Лучшие предложения по вашему стеку и формату ИП")
    analyzed_list = db.get_vacancies_by_status("ANALYZED")
    top_matches = [v for v in analyzed_list if v["ai_score"] >= 4]