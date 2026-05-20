import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

# Используем google-genai коннектор 
from langchain_google_genai import ChatGoogleGenerativeAI

# Импортируем наши промпты и схемы
from src.analyzer.prompts import ANALYZE_PROMPT_TEMPLATE
from src.analyzer.schemas import VacancyMatchingResult

# Включаем использование Vertex AI через переменную окружения
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"

# Настройки проекта (подставь свои актуальные данные)
PROJECT_ID = "project-0a1ece04-f585-4dd2-98a" 
LOCATION = "global" 

# 1. Инициализируем базовую модель
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash", 
    project=PROJECT_ID,
    location=LOCATION,
    temperature=0.2, 
    max_output_tokens=8192
)

# 2. Настраиваем строгий структурированный вывод под нашу Pydantic схему
analyzer_llm = llm.with_structured_output(VacancyMatchingResult)


# 3. Определяем структуру Состояния (State) нашего графа
class AnalyzerState(TypedDict):
    my_profile: str
    vacancy_name: str
    employer_name: str
    key_skills: str
    vacancy_description: str
    # Сюда запишется финальный объект после вызова модели
    result: Optional[VacancyMatchingResult]


# 4. Создаем узел (Node) для обработки вакансии
def analyze_vacancy_node(state: AnalyzerState) -> dict:
    """Узел графа: форматирует промпт, вызывает ИИ и возвращает результат"""
    
    # Подставляем данные из стейта в шаблон промпта
    prompt_messages = ANALYZE_PROMPT_TEMPLATE.format_messages(
        my_profile=state["my_profile"],
        employer_name=state["employer_name"],
        vacancy_name=state["vacancy_name"],
        key_skills=state["key_skills"],
        vacancy_description=state["vacancy_description"]
    )
    
    # Отправляем запрос в Gemini
    ai_response = analyzer_llm.invoke(prompt_messages)
    
    # Обновляем стейт графа
    return {"result": ai_response}


# 5. Сборка графа LangGraph
workflow = StateGraph(AnalyzerState)

# Добавляем наш узел в граф
workflow.add_node("analyze_vacancy", analyze_vacancy_node)

# Задаем ребра (направление движения данных)
workflow.add_edge(START, "analyze_vacancy")
workflow.add_edge("analyze_vacancy", END)

# Компилируем готовое приложение-граф
analyzer_app = workflow.compile()


def run_vacancy_analysis(my_profile: str, vacancy_data: dict) -> VacancyMatchingResult:
    """
    Удобная функция-обертка для запуска графа из внешних модулей.
    Принимает текст резюме и словарь с данными вакансии из БД.
    """
    inputs = {
        "my_profile": my_profile,
        "vacancy_name": vacancy_data.get("name", "Не указано"),
        "employer_name": vacancy_data.get("employer_name", "Не указано"),
        "key_skills": vacancy_data.get("key_skills", ""),
        "vacancy_description": vacancy_data.get("description", "")
    }
    
    # Запускаем граф
    final_state = analyzer_app.invoke(inputs)
    
    return final_state["result"]