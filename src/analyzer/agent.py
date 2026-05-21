from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import ChatPromptTemplate

from src.analyzer.prompts import ANALYZE_PROMPT_TEMPLATE
from src.analyzer.schemas import VacancyMatchingResult
from src.analyzer.llm_factory import get_vertex_llm  # Импортируем нашу фабрику

# 1. Получаем единый настроенный объект модели
llm = get_vertex_llm()

# 2. Настраиваем строгий структурированный вывод под Pydantic схему
analyzer_llm = llm.with_structured_output(VacancyMatchingResult)


# === Дальнейшая логика LangGraph графа остается прежней ===

class AnalyzerState(TypedDict):
    my_profile: str
    vacancy_name: str
    employer_name: str
    key_skills: str
    vacancy_description: str
    result: Optional[VacancyMatchingResult]

def analyze_vacancy_node(state: AnalyzerState) -> dict:
    prompt_messages = ANALYZE_PROMPT_TEMPLATE.format_messages(
        my_profile=state["my_profile"],
        employer_name=state["employer_name"],
        vacancy_name=state["vacancy_name"],
        key_skills=state["key_skills"],
        vacancy_description=state["vacancy_description"]
    )
    ai_response = analyzer_llm.invoke(prompt_messages)
    return {"result": ai_response}

workflow = StateGraph(AnalyzerState)
workflow.add_node("analyze_vacancy", analyze_vacancy_node)
workflow.add_edge(START, "analyze_vacancy")
workflow.add_edge("analyze_vacancy", END)

analyzer_app = workflow.compile()

def run_vacancy_analysis(my_profile: str, vacancy_data: dict) -> VacancyMatchingResult:
    inputs = {
        "my_profile": my_profile,
        "vacancy_name": vacancy_data.get("name", "Не указано"),
        "employer_name": vacancy_data.get("employer_name", "Не указано"),
        "key_skills": vacancy_data.get("key_skills", ""),
        "vacancy_description": vacancy_data.get("description", "")
    }
    final_state = analyzer_app.invoke(inputs)
    return final_state["result"]

def run_vacancy_analysis_batch(my_profile: str, vacancies_data: List[dict], batch_size: int = 10) -> List[tuple]:
    """
    Пакетный ИИ-анализ списка вакансий пачками по batch_size штук.
    Принимает список сырых вакансий из БД.
    Возвращает список кортежей (vacancy_data, VacancyMatchingResult или None).
    """
    results = []
    
    for i in range(0, len(vacancies_data), batch_size):
        chunk = vacancies_data[i:i + batch_size]
        print(f"\n[AI BATCH] Отправка пакета {i//batch_size + 1}: {len(chunk)} вакансий...")
        
        inputs_list = []
        for v in chunk:
            # Превращаем key_skills (хранящиеся в БД как JSON-строка) в строку через запятую для промпта
            skills_raw = v.get("key_skills", "")
            skills_str = ""
            if skills_raw:
                try:
                    import json
                    skills_list = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
                    skills_str = ", ".join(skills_list) if isinstance(skills_list, list) else str(skills_list)
                except Exception:
                    skills_str = str(skills_raw)

            inputs_list.append({
                "my_profile": my_profile,
                "vacancy_name": v.get("name", "Не указано"),
                "employer_name": v.get("employer_name", "Не указано"),
                "key_skills": skills_str,
                "vacancy_description": v.get("description", "")
            })
            
        # Запускаем батч параллельно с ограничением concurrency
        # return_exceptions=True возвращает объект Exception вместо выброса ошибки
        batch_outputs = analyzer_app.batch(
            inputs_list,
            config={"max_concurrency": batch_size},
            return_exceptions=True
        )
        
        for v, out in zip(chunk, batch_outputs):
            if isinstance(out, Exception):
                print(f"[AI BATCH] ❌ Ошибка при анализе вакансии ID {v['id']}: {out}")
                results.append((v, None))
            elif out and "result" in out:
                results.append((v, out["result"]))
            else:
                print(f"[AI BATCH] ⚠️ Неизвестный ответ для вакансии ID {v['id']}: {out}")
                results.append((v, None))
                
    return results