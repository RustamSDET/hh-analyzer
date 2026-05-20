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

def render_vacancy_card(v: dict):
    """Рендерит одну вакансию внутри выпадающего списка (expander)"""
    # Парсим JSON с аналитикой ИИ, который мы сохранили в БД
    try:
        ai = json.loads(v["ai_reasons"])
    except (TypeError, json.JSONDecodeError):
        ai = None

    # Формируем заголовок карточки
    score_label = get_score_badge(v["ai_score"]) if ai else "⏳ Без оценки"
    expander_title = f"{score_label} | {v['name']} ({v['employer_name']})"
    
    with st.expander(expander_title):
        # Верхняя панель с быстрыми метриками
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

        # Итоговый вердикт ИИ
        st.markdown(f"💡 **Резюме ИИ:** *{ai.get('summary', 'Нет описания')}*")
        st.markdown(f"💼 **Анализ формата оформления:** {ai.get('ip_analysis_reason', '')}")
        
        # Блок Red Flags (выводим только если они есть)
        red_flags = ai.get("red_flags", [])
        if red_flags:
            st.warning("🚨 **Критические замечания (Red Flags):**\n" + "\n".join([f"- {flag}" for flag in red_flags]))

        # Две колонки: Плюсы и Минусы
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("✅ **Плюсы соответствия:**")
            for pro in ai.get("pros", []):
                st.markdown(f"- {pro}")
        with c2:
            st.markdown("❌ **Минусы / Чего не хватает:**")
            for con in ai.get("cons", []):
                st.markdown(f"- {con}")