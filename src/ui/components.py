import streamlit as st
import json

def get_score_badge(score: int) -> str:
    """Возвращает форматированную строку с цветным маркером для оценки"""
    colors = {5: "🟢", 4: "🍏", 3: "🟡", 2: "🟠", 1: "🔴"}
    return f"{colors.get(score, '⚪')} {score}/5"

def get_ip_badge(chance: str) -> str:
    """Возвращает понятный статус для шансов работы по ИП"""
    badges = {
        "High": "🚀 Высокий (B2B/ИП)",
        "Medium": "⚡️ Средний (Надо уточнять)",
        "Low": "⚠️ Низкий (Скорее всего ТК)",
        "Impossible": "🚫 Только ТК РФ (Госкомпания/Корпорация)"
    }
    return badges.get(chance, chance)

def render_vacancy_card(v: dict, db):
    """
    🟢 Рендерит интерактивную карточку вакансии.
    Принимает объект бд для мгновенного изменения статусов воронки.
    """
    try:
        ai = json.loads(v["ai_reasons"])
    except (TypeError, json.JSONDecodeError):
        ai = None

    score_label = get_score_badge(v["ai_score"]) if ai else "⏳ Без оценки"
    expander_title = f"{score_label} | {v['name']} ({v['employer_name']})"
    
    with st.expander(expander_title):
        col1, col2 = st.columns([2, 3])
        with col1:
            if ai:
                st.markdown(f"**Шансы на ИП:**\n`{get_ip_badge(ai.get('ip_cooperation_chance'))}`")
        with col2:
            st.markdown(f"**Ссылка на вакансию:**\n[{v['alternate_url']}]({v['alternate_url']})")
            
        st.markdown("---")
        
        if not ai:
            st.info("Вакансия еще не проходила ИИ-скрининг. Нажмите кнопку запуска в боковой панели.")
            return

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

        # 🟢 ДОБАВЛЕНИЕ: Интерактивный блок кнопок управления воронкой соискателя
        st.markdown("---")
        b_col1, b_col2, _ = st.columns([1.2, 1.2, 2])
        
        with b_col1:
            # Кнопка отклика
            if st.button("🚀 Откликнулся", key=f"apply_{v['id']}", use_container_width=True):
                db.update_user_status(v["id"], "APPLIED")
                st.toast(f"Статус обновлен: Откликнулся на {v['name']}! 🚀")
                st.rerun()
                
        with b_col2:
            # Кнопка скрытия
            if st.button("❌ Не подходит", key=f"reject_{v['id']}", use_container_width=True):
                db.update_user_status(v["id"], "REJECTED")
                st.toast(f"Вакансия {v['employer_name']} скрыта из витрины")
                st.rerun()

def render_archive_vacancy_card(v: dict, db):
    """
    🟢 Рендерит интерактивную карточку вакансии для вкладки "Полный архив воронки".
    Позволяет менять статус пользователя через выпадающий список и раскрывать подробности,
    включая исходный распарсенный JSON от ИИ.
    """
    try:
        ai = json.loads(v["ai_reasons"])
    except (TypeError, json.JSONDecodeError):
        ai = None

    score_label = get_score_badge(v["ai_score"]) if ai else "⏳ Без оценки"
    
    u_status = v.get("user_status", "CONSIDERING")
    status_label_map = {
        "CONSIDERING": "⏳ На рассмотрении",
        "APPLIED": "🚀 Откликнулся",
        "REJECTED": "❌ Не подходит"
    }
    current_label = status_label_map.get(u_status, u_status)
    
    expander_title = f"{score_label} | {v['name']} ({v['employer_name']}) — {current_label}"
    
    with st.expander(expander_title):
        col1, col2 = st.columns([2, 3])
        with col1:
            status_options = ["⏳ На рассмотрении", "🚀 Откликнулся", "❌ Не подходит"]
            status_keys = ["CONSIDERING", "APPLIED", "REJECTED"]
            
            try:
                current_index = status_keys.index(u_status)
            except ValueError:
                current_index = 0
                
            selected_label = st.selectbox(
                "Изменить статус воронки:",
                options=status_options,
                index=current_index,
                key=f"archive_status_select_{v['id']}"
            )
            
            new_status = status_keys[status_options.index(selected_label)]
            if new_status != u_status:
                db.update_user_status(v["id"], new_status)
                st.toast(f"Статус вакансии '{v['name']}' изменен на: {selected_label}! 🎯")
                st.rerun()
                
        with col2:
            st.markdown(f"🔗 **Ссылка на HH.ru:**\n[{v['alternate_url']}]({v['alternate_url']})")
            st.markdown(f"📅 **Дата сбора:** {v['created_at']}")
            
        st.markdown("---")
        
        if not ai:
            st.info("Вакансия еще не проходила ИИ-скрининг.")
            return

        st.markdown(f"💡 **Резюме ИИ:** *{ai.get('summary', 'Нет описания')}*")
        st.markdown(f"💼 **Анализ формата оформления:** {ai.get('ip_analysis_reason', '')}")
        if ai.get("ip_cooperation_chance"):
            st.markdown(f"🎯 **Шансы работы по ИП:** `{get_ip_badge(ai.get('ip_cooperation_chance'))}`")
            
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
        with st.expander("⚙️ Исходный JSON-вердикт от ИИ"):
            st.json(ai)