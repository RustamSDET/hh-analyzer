import streamlit as st
import os
import sys
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database import DBManager
from src.parser import HHWebClient
from src.analyzer import run_vacancy_analysis
from src.ui.components import render_vacancy_card

# Отключаем лишний шум предупреждений библиотек гугла в консоли Streamlit
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

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
total_failed = len(db.get_vacancies_by_status("FAILED"))
analyzed_list = db.get_vacancies_by_status("ANALYZED")

# Подсчитываем статусы воронки среди проанализированных
total_considering = len([v for v in analyzed_list if v.get("user_status", "CONSIDERING") == "CONSIDERING"])
total_applied = len([v for v in analyzed_list if v.get("user_status") == "APPLIED"])
total_rejected = len([v for v in analyzed_list if v.get("user_status") == "REJECTED"])

st.sidebar.text(f"Новые (только ID): {total_new}")
st.sidebar.text(f"Спарсенные (ожидают ИИ): {total_parsed}")
st.sidebar.text(f"Ошибки анализа (FAILED): {total_failed}")
st.sidebar.markdown("---")
st.sidebar.subheader("📈 Воронка соискателя")
st.sidebar.text(f"⏳ На рассмотрении: {total_considering}")
st.sidebar.text(f"🚀 Откликов отправлено: {total_applied}")
st.sidebar.text(f"❌ Архив (Не подошли): {total_rejected}")
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
        
        try:
            search_page = client.fetch_vacancies_page(page=0)
            search_result = search_page.get("vacancySearchResult", {})
            found_items = search_result.get("vacancies", [])
            
            print(f"[UI PATH] Фаза 1: Передаем {len(found_items)} вакансий в БД...")
            db.save_discovered_vacancies(found_items)
        except Exception as e:
            st.sidebar.error(f"Ошибка поиска: {e}")
            
        new_vacancies = db.get_vacancies_by_status("NEW")
        for idx, v in enumerate(new_vacancies):
            v_id = v["id"]
            log_area.caption(f"Парсинг {idx+1}/{len(new_vacancies)}: ID {v_id}")
            try:
                raw_details = client.fetch_vacancy_details(v_id)
                db.update_vacancy_details(
                    vacancy_id=v_id,
                    description=raw_details.get("description", ""),
                    key_skills=raw_details.get("key_skills", [])
                )
            except Exception as e:
                db.mark_as_failed(v_id)
        
        st.sidebar.success("Сбор данных успешно завершен!")
        st.rerun()

# --- КНОПКА 2: ИИ-СКРИНИНГ ---
if st.sidebar.button("🤖 2. Запустить ИИ-скрининг", use_container_width=True):
    if not my_profile_text:
        st.sidebar.error("Сначала создайте файл my_profile.txt в корне!")
    else:
        parsed_vacancies = db.get_vacancies_by_status("PARSED") + db.get_vacancies_by_status("FAILED")
        
        if not parsed_vacancies:
            st.sidebar.info("Нет вакансий для анализа ИИ.")
        else:
            progress_bar = st.sidebar.progress(0.0)
            log_area = st.sidebar.empty()
            
            for idx, v in enumerate(parsed_vacancies):
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
                except Exception as e:
                    db.mark_as_failed(v["id"])
                    
                progress_bar.progress((idx + 1) / len(parsed_vacancies))
                
            st.sidebar.success("ИИ-анализ успешно завершен!")
            st.rerun()

# ==========================================
# ГЛАВНЫЙ ЭКРАН: Отображение результатов
# ==========================================
st.title("🕵️‍♂️ Персональный ИИ-Скрининг Вакансий")
tab1, tab2, tab3 = st.tabs(["🔥 Новые Топ Матчи (Оценка 4-5)", "📂 Полный Архив воронки", "📄 Твое Резюме"])

with tab1:
    st.subheader("Витрина актуальных предложений (на рассмотрении)")
    
    # 🟢 ФИКС: Оставляем на витрине только вакансии с оценкой >= 4, которые соискатель ЕЩЕ НЕ ОБРАБОТАЛ
    top_matches = [
        v for v in analyzed_list 
        if v["ai_score"] >= 4 and v.get("user_status", "CONSIDERING") == "CONSIDERING"
    ]
    
    if not top_matches:
        st.info("Пока нет новых идеальных совпадений. Все подходящие вакансии обработаны или архив пуст.")
    else:
        top_matches.sort(key=lambda x: x["created_at"], reverse=True)
        for vacancy in top_matches:
            # Передаем объект бд в карточку для работы кнопок
            render_vacancy_card(vacancy, db)

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
                
            # Красиво мапим статусы пользователя для интерактивной таблицы
            u_status = v.get("user_status", "CONSIDERING")
            status_map = {
                "CONSIDERING": "⏳ На рассмотрении",
                "APPLIED": "🚀 Откликнулся",
                "REJECTED": "❌ Не подходит"
            }
                
            table_data.append({
                "ID": v["id"],
                "Название": v["name"],
                "Компания": v["employer_name"],
                "Оценка ИИ": v["ai_score"],
                "Шанс ИП": ip_chance,
                "Статус воронки": status_map.get(u_status, u_status),
                "Дата сбора": v["created_at"]
            })
        st.dataframe(table_data, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Профиль кандидата (из my_profile.txt)")
    if my_profile_text:
        st.code(my_profile_text, language="markdown")
    else:
        st.warning("Файл my_profile.txt не найден в корне проекта.")