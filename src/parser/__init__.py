from .client import HHWebClient
from .schemas import VacancyDetails, VacancyListItem
from .utils import clean_html

# Определяем, что будет доступно при импорте "from src.parser import *"
__all__ = ["HHWebClient", "VacancyDetails", "VacancyListItem", "clean_html"]