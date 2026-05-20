import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

# Импортируем выделенный коннектор для Google Cloud Vertex AI
from langchain_google_vertexai import ChatVertexAI

from src.analyzer.prompts import ANALYZE_PROMPT_TEMPLATE
from src.analyzer.schemas import VacancyMatchingResult

# Жесткие настройки твоего облачного проекта Google Cloud
PROJECT_ID = "project-0a1ece04-f585-4dd2-98a" 
LOCATION = "us-central1" 

# Инициализируем модель строго через Vertex AI интерфейс
llm = ChatVertexAI(
    model="gemini-1.5-flash", # или gemini-2.5-flash в зависимости от того, что развернуто в GCP
    project=PROJECT_ID,
    location=LOCATION,
    temperature=0.2, 
    max_output_tokens=8192
)

# Настраиваем строгий структурированный вывод под нашу Pydantic схему
analyzer_llm = llm.with_structured_output(VacancyMatchingResult)

# --- Логика LangGraph графа остается без изменений ---
class AnalyzerState(TypedDict):
    my_profile: str
    vacancy_name: str
    employer_name: str
    key_skills: str
    vacancy_description: str
    result: Optional[VacancyMatchingResult]

def analyze_vacancy_node(state: AnalyzerState) -> dict:
    """Узел графа: форматирует промпт, вызывает ИИ и возвращает результат"""
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
    """Обертка для запуска анализа вакансии"""
    inputs = {
        "my_profile": my_profile,
        "vacancy_name": vacancy_data.get("name", "Не указано"),
        "employer_name": vacancy_data.get("employer_name", "Не указано"),
        "key_skills": vacancy_data.get("key_skills", ""),
        "vacancy_description": vacancy_data.get("description", "")
    }
    final_state = analyzer_app.invoke(inputs)
    return final_state["result"]