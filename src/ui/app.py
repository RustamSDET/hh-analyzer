import streamlit as st
import os
import sys
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.database import DBManager
from src.parser import HHWebClient
from src.analyzer import run_vacancy_analysis, run_vacancy_analysis_batch
from src.ui.components import (
    render_vacancy_card, 
    render_archive_vacancy_card, 
    get_ip_badge,
    get_grade_badge,
    get_stack_badge,
    get_remote_badge
)

# Отключаем лишний шум предупреждений библиотек гугла в консоли Streamlit
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

st.set_page_config(page_title="QA Job AI Analyzer", page_icon="🕵️‍♂️", layout="wide")

db = DBManager()

# Инициализируем переменные состояния для безопасного управления диалогом
if "table_key_version" not in st.session_state:
    st.session_state["table_key_version"] = 0
if "selected_vacancy" not in st.session_state:
    st.session_state["selected_vacancy"] = None

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

# 🟢 ОПТИМИЗАЦИЯ: Один легкий запрос статистики вместо 4 раздельных тяжелых запросов
db_stats = db.get_database_stats()
total_new = db_stats.get("NEW", 0)
total_parsed = db_stats.get("PARSED", 0)
total_failed = db_stats.get("FAILED", 0)

# 🟢 ОПТИМИЗАЦИЯ: Загружаем только легкие метаданные без полей descriptions/key_skills
analyzed_list = db.get_analyzed_vacancies_for_ui()

# Подсчитываем статусы воронки среди проанализированных (в памяти, мгновенно)
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
            
        import random
        import time
        vacancies_to_parse = db.get_vacancies_for_parsing()
        for idx, v in enumerate(vacancies_to_parse):
            v_id = v["id"]
            log_area.caption(f"Парсинг {idx+1}/{len(vacancies_to_parse)}: ID {v_id}")
            
            if idx > 0:
                delay = random.uniform(2.0, 5.0)
                time.sleep(delay)
                
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
        all_candidates = db.get_vacancies_by_status("PARSED") + db.get_vacancies_by_status("FAILED")
        parsed_vacancies = [v for v in all_candidates if v.get("description") and v["description"].strip()]
        
        if not parsed_vacancies:
            st.sidebar.info("Нет вакансий для анализа ИИ.")
        else:
            progress_bar = st.sidebar.progress(0.0)
            log_area = st.sidebar.empty()
            
            # Разделяем на пачки по 10 штук для плавного UI-прогресса
            chunk_size = 10
            total_vacancies = len(parsed_vacancies)
            
            for i in range(0, total_vacancies, chunk_size):
                chunk = parsed_vacancies[i:i + chunk_size]
                log_area.caption(f"Анализ пачки {i//chunk_size + 1}: {len(chunk)} вакансий...")
                
                # Запускаем батч ИИ-скрининга (до 10 штук параллельно)
                batch_results = run_vacancy_analysis_batch(
                    my_profile=my_profile_text,
                    vacancies_data=chunk,
                    batch_size=chunk_size
                )
                
                for v, ai_result in batch_results:
                    v_id = v["id"]
                    if ai_result is None:
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
                        db.update_ai_analysis(
                            v_id, 
                            ai_result.score, 
                            ai_result.grade_score, 
                            ai_result.remote_chance, 
                            ai_result.stack_score, 
                            json.dumps(details_dict, ensure_ascii=False)
                        )
                    except Exception:
                        db.mark_as_failed(v_id)
                
                # Обновляем прогресс бар
                progress = min((i + chunk_size) / total_vacancies, 1.0)
                progress_bar.progress(progress)
                
            st.sidebar.success("ИИ-анализ успешно завершен!")
            st.rerun()

# ==========================================
# 💬 ВСПЛЫВАЮЩЕЕ ОКНО ДЕТАЛЕЙ С JSON ОТ ИИ
# ==========================================
@st.dialog("📋 Детали вакансии и ИИ-анализ", width="large")
def show_vacancy_dialog(v: dict):
    try:
        ai = json.loads(v["ai_reasons"])
    except (TypeError, json.JSONDecodeError):
        ai = None

    st.subheader(v["name"])
    st.markdown(f"**Работодатель:** {v['employer_name']}")
    st.markdown(f"🔗 **Ссылка на HH.ru:** [{v['alternate_url']}]({v['alternate_url']})")
    st.markdown(f"📅 **Дата сбора:** {v['created_at']}")
    st.markdown("---")

    if not ai:
        st.info("Эта вакансия еще не проходила ИИ-скрининг.")
    else:
        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
        with col_d1:
            st.markdown(f"**Шансы на ИП:**\n`{get_ip_badge(ai.get('ip_cooperation_chance'))}`")
        with col_d2:
            grade_val = v.get("ai_grade_score") or ai.get("grade_score")
            st.markdown(f"**Грейд кандидата:**\n`{get_grade_badge(grade_val)}`")
        with col_d3:
            stack_val = v.get("ai_stack_score") or ai.get("stack_score")
            st.markdown(f"**Соответствие стеку:**\n`{get_stack_badge(stack_val)}`")
        with col_d4:
            remote_val = v.get("ai_remote_chance") or ai.get("remote_chance")
            st.markdown(f"**Удаленная работа:**\n`{get_remote_badge(remote_val)}`")
            
        st.markdown("---")
        st.markdown(f"💡 **Резюме ИИ:** *{ai.get('summary', 'Нет описания')}*")
        st.markdown(f"💼 **Анализ формата оформления:** {ai.get('ip_analysis_reason', '')}")
            
        red_flags = ai.get("red_flags", [])
        if red_flags:
            st.warning("🚨 **Критические замечания (Red Flags):**\n" + "\n".join([f"- {flag}" for flag in red_flags]))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("✅ **Плюсы соответствия:**")
            for pro in ai.get("pros", []):
                st.markdown(f"- {pro}")
        with c2:
            st.markdown("❌ **Минусы / Чего не хватает:**")
            for con in ai.get("cons", []):
                st.markdown(f"- {con}")

        st.markdown("---")
        st.markdown("📂 **Распарсенный JSON от ИИ:**")
        st.json(ai)

    st.markdown("---")
    
    # Смена статуса внутри диалога
    status_options = ["⏳ На рассмотрении", "🚀 Откликнулся", "❌ Не подходит"]
    status_keys = ["CONSIDERING", "APPLIED", "REJECTED"]
    u_status = v.get("user_status", "CONSIDERING")
    try:
        current_index = status_keys.index(u_status)
    except ValueError:
        current_index = 0

    selected_label = st.selectbox(
        "Изменить статус воронки:",
        options=status_options,
        index=current_index,
        key=f"dialog_status_select_{v['id']}"
    )

    new_status = status_keys[status_options.index(selected_label)]
    if new_status != u_status:
        db.update_user_status(v["id"], new_status)
        st.toast(f"Статус вакансии '{v['name']}' изменен на: {selected_label}! 🎯")
        st.rerun()

# Если в состоянии сессии есть выбранная вакансия, показываем диалог
if st.session_state["selected_vacancy"] is not None:
    vacancy_to_show = st.session_state["selected_vacancy"]
    # Очищаем сессионную переменную сразу, чтобы диалог не открылся повторно
    st.session_state["selected_vacancy"] = None
    show_vacancy_dialog(vacancy_to_show)

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
    st.subheader("📁 Интерактивный архив обработанных вакансий")
    
    # Кнопка ручного обновления данных
    if st.button("🔄 Обновить данные", key="btn_refresh_archive", use_container_width=True):
        st.rerun()
        
    if not analyzed_list:
        st.info("Архив пуст.")
    else:
        # --- ПАНЕЛЬ ФИЛЬТРОВ ---
        st.markdown("### 🔍 Панель быстрого поиска и фильтрации")
        
        search_keyword = st.text_input(
            "Поиск по названию вакансии или имени работодателя:",
            placeholder="Введите ключевые слова...",
            key="archive_search"
        )
        
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            score_filter = st.selectbox(
                "Оценка соответствия ИИ (Общая):",
                options=["Все", "5", "4", "3", "2", "1"],
                key="archive_score_filter"
            )
        with f_col2:
            status_filter = st.selectbox(
                "Текущий статус воронки:",
                options=["Все", "⏳ На рассмотрении", "🚀 Откликнулся", "❌ Не подходит"],
                key="archive_status_filter"
            )
        with f_col3:
            ip_filter = st.selectbox(
                "Шансы оформления по ИП/B2B:",
                options=["Все", "🚀 Высокий (B2B/ИП)", "⚡️ Средний (Надо уточнять)", "⚠️ Низкий (Скорее всего ТК)", "🚫 Только ТК РФ"],
                key="archive_ip_filter"
            )
            
        f_col4, f_col5, f_col6 = st.columns(3)
        with f_col4:
            grade_filter = st.selectbox(
                "Соответствие грейду:",
                options=["Все", "5", "4", "3", "2", "1"],
                key="archive_grade_filter"
            )
        with f_col5:
            stack_filter = st.selectbox(
                "Соответствие стеку:",
                options=["Все", "5", "4", "3", "2", "1"],
                key="archive_stack_filter"
            )
        with f_col6:
            remote_filter = st.selectbox(
                "Удаленная работа:",
                options=["Все", "📶 Да (Удаленка)", "🌐 Высокий шанс", "🏢 Низкий шанс / Гибрид", "❌ Нет (Только офис)"],
                key="archive_remote_filter"
            )
            
        st.markdown("---")

        # --- ФИЛЬТРАЦИЯ ДАННЫХ ---
        filtered_list = analyzed_list
        
        # 1. Текстовый поиск
        if search_keyword:
            kw = search_keyword.lower().strip()
            filtered_list = [
                v for v in filtered_list
                if kw in v["name"].lower() or kw in v["employer_name"].lower()
            ]
            
        # 2. По оценке ИИ
        if score_filter != "Все":
            target_score = int(score_filter)
            filtered_list = [v for v in filtered_list if v["ai_score"] == target_score]
            
        # 3. По статусу пользователя
        if status_filter != "Все":
            status_map_keys = {
                "⏳ На рассмотрении": "CONSIDERING",
                "🚀 Откликнулся": "APPLIED",
                "❌ Не подходит": "REJECTED"
            }
            target_status = status_map_keys[status_filter]
            filtered_list = [v for v in filtered_list if v.get("user_status", "CONSIDERING") == target_status]
            
        # 4. По шансу ИП
        if ip_filter != "Все":
            ip_chance_map = {
                "🚀 Высокий (B2B/ИП)": "High",
                "⚡️ Средний (Надо уточнять)": "Medium",
                "⚠️ Низкий (Скорее всего ТК)": "Low",
                "🚫 Только ТК РФ": "Impossible"
            }
            target_ip = ip_chance_map[ip_filter]
            
            filtered_list_with_ip = []
            for v in filtered_list:
                try:
                    ai_data = json.loads(v["ai_reasons"])
                    chance = ai_data.get("ip_cooperation_chance", "Medium")
                except Exception:
                    chance = "Medium"
                if chance == target_ip:
                    filtered_list_with_ip.append(v)
            filtered_list = filtered_list_with_ip

        # 5. По соответствию грейду
        if grade_filter != "Все":
            target_grade = int(grade_filter)
            filtered_list_with_grade = []
            for v in filtered_list:
                val = v.get("ai_grade_score")
                if val is None and v.get("ai_reasons"):
                    try:
                        val = json.loads(v["ai_reasons"]).get("grade_score")
                    except Exception:
                        pass
                if val == target_grade:
                    filtered_list_with_grade.append(v)
            filtered_list = filtered_list_with_grade

        # 6. По соответствию стеку
        if stack_filter != "Все":
            target_stack = int(stack_filter)
            filtered_list_with_stack = []
            for v in filtered_list:
                val = v.get("ai_stack_score")
                if val is None and v.get("ai_reasons"):
                    try:
                        val = json.loads(v["ai_reasons"]).get("stack_score")
                    except Exception:
                        pass
                if val == target_stack:
                    filtered_list_with_stack.append(v)
            filtered_list = filtered_list_with_stack

        # 7. По удаленной работе
        if remote_filter != "Все":
            remote_map = {
                "📶 Да (Удаленка)": "Да",
                "🌐 Высокий шанс": "Высокий шанс",
                "🏢 Низкий шанс / Гибрид": "Низкий шанс",
                "❌ Нет (Только офис)": "Нет"
            }
            target_remote = remote_map[remote_filter]
            filtered_list_with_remote = []
            for v in filtered_list:
                val = v.get("ai_remote_chance")
                if val is None and v.get("ai_reasons"):
                    try:
                        val = json.loads(v["ai_reasons"]).get("remote_chance")
                    except Exception:
                        pass
                if val == target_remote:
                    filtered_list_with_remote.append(v)
            filtered_list = filtered_list_with_remote

        # --- СОРТИРОВКА И ВЫВОД РЕЗУЛЬТАТОВ ---
        filtered_list.sort(key=lambda x: x["created_at"], reverse=True)
        total_found = len(filtered_list)
        
        st.write(f"Найдено вакансий по фильтрам: **{total_found}**")
        
        if total_found == 0:
            st.info("Нет вакансий, соответствующих заданным критериям фильтрации.")
        else:
            # Формируем плоский список словарей для таблицы st.dataframe
            table_data = []
            for v in filtered_list:
                # Достаем шанс ИП из ai_reasons
                try:
                    ai_data = json.loads(v["ai_reasons"]) if v.get("ai_reasons") else {}
                    ip_chance = ai_data.get("ip_cooperation_chance", "Medium")
                except Exception:
                    ai_data = {}
                    ip_chance = "Medium"
                
                # Форматируем шанс ИП на русском языке
                ip_badge = get_ip_badge(ip_chance)
                
                # Форматируем статус воронки на русском языке
                u_status = v.get("user_status", "CONSIDERING")
                status_label_map = {
                    "CONSIDERING": "⏳ На рассмотрении",
                    "APPLIED": "🚀 Откликнулся",
                    "REJECTED": "❌ Не подходит"
                }
                status_label = status_label_map.get(u_status, u_status)
                
                # Форматируем оценку ИИ
                ai_score_val = v.get("ai_score")
                score_label = f"⭐ {ai_score_val}/5" if ai_score_val is not None else "⏳ Без оценки"
                
                grade_val = v.get("ai_grade_score") or ai_data.get("grade_score")
                grade_label = f"🎯 {grade_val}/5" if grade_val is not None else "⏳ N/A"
                
                stack_val = v.get("ai_stack_score") or ai_data.get("stack_score")
                stack_label = f"💻 {stack_val}/5" if stack_val is not None else "⏳ N/A"
                
                remote_val = v.get("ai_remote_chance") or ai_data.get("remote_chance")
                remote_label = f"📶 {remote_val}" if remote_val is not None else "⏳ N/A"
                
                table_data.append({
                    "ID": v["id"],
                    "Название": v["name"],
                    "Компания": v["employer_name"],
                    "Общая оценка ИИ": score_label,
                    "Грейд": grade_label,
                    "Стек": stack_label,
                    "Удаленка": remote_label,
                    "Шанс ИП": ip_badge,
                    "Статус воронки": status_label,
                    "Дата сбора": v["created_at"]
                })
            
            # Отображаем плоскую интерактивную таблицу с динамическим ключом
            selection = st.dataframe(
                table_data,
                on_select="rerun",
                selection_mode="single-row",
                key=f"archive_table_{st.session_state['table_key_version']}",
                width="stretch"
            )
            
            # Безопасное извлечение выделенных строк из st.dataframe
            rows = []
            if selection is not None:
                if hasattr(selection, "selection"):
                    sel_dict = selection.selection
                    if isinstance(sel_dict, dict) and "rows" in sel_dict:
                        rows = sel_dict["rows"]
                    elif hasattr(sel_dict, "rows"):
                        rows = sel_dict.rows
                elif isinstance(selection, dict) and "selection" in selection:
                    sel_dict = selection["selection"]
                    if isinstance(sel_dict, dict) and "rows" in sel_dict:
                        rows = sel_dict["rows"]
            
            if rows:
                selected_row_idx = rows[0]
                v = filtered_list[selected_row_idx]
                
                # Записываем в session_state и увеличиваем версию ключа таблицы для сброса выделения
                st.session_state["selected_vacancy"] = v
                st.session_state["table_key_version"] += 1
                st.rerun()

with tab3:
    st.subheader("Профиль кандидата (из my_profile.txt)")
    if my_profile_text:
        st.code(my_profile_text, language="markdown")
    else:
        st.warning("Файл my_profile.txt не найден в корне проекта.")