import streamlit as st
import os
import sys
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database import DBManager
from src.parser import HHWebClient, VacancyDetails
from src.analyzer import run_vacancy_analysis
from src.ui.components import render_vacancy_card

st.set_page_config(page_title="QA Job AI Analyzer", page_icon="🕵️‍♂️", layout="wide")

db = DBManager()

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

if st.sidebar.button("🔄 1. Собрать вакансии за 24ч", use_container_width=True):
    print("\n==================================================")
    print("[UI BUTTON] Нажата кнопка '1. Собрать вакансии за 24ч'")
    print("==================================================")
    
    with st.spinner("Запрос к HH.ru и скачивание деталей..."):
        log_area = st.sidebar.empty()
        client = HHWebClient()
        
        # --- ФАЗА 1 ---
        print("[UI PATH] >>> Запуск Фазы 1 (Поиск ID) внутри UI...")
        log_area.caption("Поиск свежих ID...")
        try:
            search_page = client.fetch_vacancies_page(page=0)
            print("[UI PATH] Фаза 1: Сетевой ответ получен. Парсим структуру...")
            
            # Исправленные ключи веб-структуры
            search_result = search_page.get("vacancySearchResult", {})
            found_items = search_result.get("vacancies", [])
            found_ids = [str(item["vacancyId"]) for item in found_items if "vacancyId" in item]
            
            print(f"[UI PATH] Фаза 1: Найдено {len(found_ids)} вакансий. Сохраняем в SQLite...")
            db.save_discovered_ids(found_ids)
            print("[UI PATH] Фаза 1: Успешно записано в базу данных.")
        except Exception as e:
            print(f"[UI PATH] 💥 Ошибка на Фазе 1: {e}")
            st.sidebar.error(f"Ошибка поиска: {e}")
            
        # --- ФАЗА 2 ---
        print("\n[UI PATH] >>> Переход к Фазе 2 (Скачивание HTML-описаний)...")
        new_vacancies = db.get_vacancies_by_status("NEW")
        print(f"[UI PATH] Из базы извлечено {len(new_vacancies)} вакансий в статусе NEW.")
        
        for idx, v in enumerate(new_vacancies):
            v_id = v["id"]
            print(f"[UI PATH] Цикл Фазы 2: Обработка {idx+1}/{len(new_vacancies)} (ID: {v_id})")
            log_area.caption(f"Парсинг {idx+1}/{len(new_vacancies)}: ID {v_id}")
            try:
                raw_details = client.fetch_vacancy_details(v_id)
                print(f"[UI PATH] HTML страницы ID {v_id} успешно скачан и очищен.")
                
                # Собираем детальки (описание уже лежит в чистом виде внутри ключа description)
                vacancy_obj = VacancyDetails.from_raw_json(raw_details, raw_details.get("description", ""))
                
                print(f"[UI PATH] Обновляем статус в БД на 'PARSED' для вакансии: {vacancy_obj.name}")
                db.update_vacancy_details(vacancy_obj)
            except Exception as e:
                print(f"[UI PATH] ❌ Ошибка скачивания карточки ID {v_id}: {e}")
                db.mark_as_failed(v_id)
        
        print("[UI PATH] 🎉 ВСЕ ФАЗЫ ПАРСИНГА УСПЕШНО ВЫПОЛНЕНЫ!")
        st.sidebar.success("Сбор данных успешно завершен!")
        st.rerun()

if st.sidebar.button("🤖 2. Запустить ИИ-скрининг", use_container_width=True):
    print("\n==================================================")
    print("[UI BUTTON] Нажата кнопка '2. Запустить ИИ-скрининг'")
    print("==================================================")
    if not my_profile_text:
        st.sidebar.error("Сначала создайте файл my_profile.txt в корне!")
    else:
        parsed_vacancies = db.get_vacancies_by_status("PARSED")
        print(f"[UI PATH] Найдено {len(parsed_vacancies)} вакансий для ИИ-анализа.")
        
        if not parsed_vacancies:
            st.sidebar.info("Нет вакансий для анализа ИИ.")
        else:
            progress_bar = st.sidebar.progress(0.0)
            log_area = st.sidebar.empty()
            
            for idx, v in enumerate(parsed_vacancies):
                print(f"[UI PATH] ИИ-Анализ {idx+1}/{len(parsed_vacancies)}: {v['name']} ({v['employer_name']})")
                log_area.caption(f"Анализ {idx+1}/{len(parsed_vacancies)}: {v['name']}")
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
                    db.update_ai_analysis(v["id"], ai_result.score, json.dumps(details_dict, ensure_ascii=False))
                    print(f"[UI PATH] -> Оценка {ai_result.score} успешно сохранена.")
                except Exception as e:
                    print(f"[UI PATH] ❌ Ошибка выполнения ИИ-модели для ID {v['id']}: {e}")
                    db.mark_as_failed(v["id"])
                    
                progress_bar.progress((idx + 1) / len(parsed_vacancies))
                
            print("[UI PATH] 🎉 ИИ-АНАЛИЗ ВСЕХ ВАКАНСИЙ С ЗАВЕРШЕН!")
            st.sidebar.success("ИИ-анализ успешно завершен!")
            st.rerun()

# ==========================================
# ГЛАВНЫЙ ЭКРАН (Остается без изменений)
# ==========================================
st.title("🕵️‍♂️ Персональный ИИ-Скрининг Вакансий")
tab1, tab2, tab3 = st.tabs(["🔥 Топ Матчи (Оценка 4-5)", "📂 Все проанализированные", "📄 Твое Резюме"])

with tab1:
    st.subheader("Лучшие предложения по вашему стеку и формату ИП")
    analyzed_list = db.get_vacancies_by_status("ANALYZED")
    top_matches = [v for v in analyzed_list if v["ai_score"] >= 4]
    
    if not top_matches:
        st.info("Пока нет идеальных совпадений. Запустите сбор и анализ вакансий.")
    else:
        top_matches.sort(key=lambda x: x["created_at"], reverse=True)
        for vacancy in top_matches:
            render_vacancy_card(vacancy)

with tab2:
    st.subheader("Полный архив обработанных вакансий")
    if not analyzed_list:
        st.info("Архив пуст.")
    else:
        table_data = []
        for v in analyzed_list:
            try:
                ai_data = json.loads(v["ai_reasons"])
                ip_chance = ai_data.get("ip_cooperation_chance", "Medium")
            except Exception:
                ip_chance = "Error"
                
            table_data.append({
                "ID": v["id"],
                "Название": v["name"],
                "Компания": v["employer_name"],
                "Оценка ИИ": v["ai_score"],
                "Шанс ИП": ip_chance,
                "Дата сбора": v["created_at"]
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Профиль кандидата (из my_profile.txt)")
    if my_profile_text:
        st.code(my_profile_text, language="markdown")
    else:
        st.warning("Файл my_profile.txt не найден в корне проекта.")