import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from src.analyzer.prompts import ANALYZE_PROMPT_TEMPLATE
from src.analyzer.schemas import VacancyMatchingResult

# 🟢 ИСПРАВЛЕНИЕ: Гарантируем правильную конфигурацию переменных среды для SDK v4+
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = "project-0a1ece04-f585-4dd2-98a"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"

# Инициализируем модель через твой привычный интерфейс
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash", 
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],
    vertexai=True,  # Принудительное удержание рельс Vertex
    temperature=0.2, 
    max_output_tokens=8192
)

analyzer_llm = llm.with_structured_output(VacancyMatchingResult)

# === Дальнейшая логика графа LangGraph ===
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