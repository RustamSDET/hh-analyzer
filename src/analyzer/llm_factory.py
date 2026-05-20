import os
# Импортируем официальный коннектор Vertex AI для LangChain
from langchain_google_vertexai import ChatVertexAI

def get_vertex_llm() -> ChatVertexAI:
    """
    Единая точка инициализации модели Gemini через официальный Vertex AI бэкэнд.
    Строго использует инфраструктуру Google Cloud Platform.
    """
    # Твой подтвержденный Project ID и стабильный регион
    PROJECT_ID = "project-0a1ece04-f585-4dd2-98a"
    LOCATION = "global"

    # Инициализируем модель строго по документации langchain-google-vertexai
    return ChatVertexAI(
        model="gemini-3.5-flash",  # Твоя новейшая модель из Vertex AI Model Garden
        project=PROJECT_ID,
        location=LOCATION,
        temperature=0.2,
        max_output_tokens=8192
    )