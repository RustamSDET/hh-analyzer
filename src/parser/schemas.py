from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any

# --- Базовый конфиг под Pydantic v2 ---
class WebBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,       # Позволяет мапить поля по алиасам (camelCase)
        arbitrary_types_allowed=True
    )

class WebCompany(WebBaseModel):
    """Вспомогательная модель для разбора компании из веб-выдачи"""
    id: Optional[int] = None
    name: Optional[str] = None
    accredited_it_employer: Optional[bool] = Field(None, alias="accreditedITEmployer")


# ========================================================
# ФАЗА 1: Модели для парсинга поисковой выдачи
# ========================================================

class VacancyListItem(WebBaseModel):
    """
    Обновленная схема для Фазы 1.
    Она подменяет camelCase поля на удобный snake_case и автоматически 
    генерирует правильную ссылку на вакансию.
    """
    id: str = Field(..., alias="vacancyId")  # Мапим веб-поле vacancyId в стандартный id
    name: str
    company: Optional[WebCompany] = None

    @property
    def alternate_url(self) -> str:
        """Автоматически собирает человеческую ссылку на вакансию"""
        return f"https://hh.ru/vacancy/{self.id}"


class HHWebSearchResponse(WebBaseModel):
    """Корневой парсер ответа. Безжалостно выкидывает 95% мусора из 10 тыс. строк лога"""
    vacancies: List[VacancyListItem] = Field([], alias="vacancies")
    total_results: int = Field(0, alias="totalResults")

    @classmethod
    def from_raw_json(cls, data: dict) -> "HHWebSearchResponse":
        """Фабрика для безопасного извлечения данных из узла vacancySearchResult"""
        search_result = data.get("vacancySearchResult", {})
        return cls(
            vacancies=search_result.get("vacancies", []),
            total_results=search_result.get("totalResults", 0)
        )


# ========================================================
# ФАЗА 2: Модель для сохранения в БД и отправки в ИИ
# ========================================================

class VacancyDetails(BaseModel):
    """
    Финальная плоская структура вакансии. 
    Она остается неизменной для БД и Gemini, защищая остальное приложение от изменений на HH.
    """
    id: str
    name: str
    description: str
    alternate_url: str
    employer_name: str
    key_skills: List[str]

    @classmethod
    def from_raw_json(cls, raw_data: dict, clean_description: str) -> "VacancyDetails":
        """
        Всеядный фабричный метод. Умеет собирать детали вакансии как из старого API, 
        так и из новых веб-объектов, страхуя нас от падений.
        """
        # 1. Вычисляем ID (в API это id, на вебе это может быть vacancyId)
        v_id = str(raw_data.get("id") or raw_data.get("vacancyId", ""))
        
        # 2. Вычисляем имя работодателя (в API: employer.name, на вебе: company.name)
        employer_name = "Не указан"
        if "company" in raw_data and isinstance(raw_data["company"], dict):
            employer_name = raw_data["company"].get("name", "Не указан")
        elif "employer" in raw_data and isinstance(raw_data["employer"], dict):
            employer_name = raw_data["employer"].get("name", "Не указан")
            
        # 3. Безопасно парсим навыки (в поиске их нет, но они прилетят из карточки описания)
        raw_skills = raw_data.get("key_skills", [])
        skills = []
        if isinstance(raw_skills, list):
            for skill in raw_skills:
                if isinstance(skill, dict) and "name" in skill:
                    skills.append(skill["name"])
                elif isinstance(skill, str):
                    skills.append(skill)

        # 4. Ссылка на вакансию
        alternate_url = raw_data.get("alternate_url") or f"https://hh.ru/vacancy/{v_id}"

        return cls(
            id=v_id,
            name=raw_data.get("name", "Не указано"),
            description=clean_description,
            alternate_url=alternate_url,
            employer_name=employer_name,
            key_skills=skills
        )