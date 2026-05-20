from typing import TypedDict, Optional
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