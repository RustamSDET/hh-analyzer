import logging
import requests
import time
from typing import Dict, Any
from bs4 import BeautifulSoup

# Imporitng manual configs
from src.config import RAW_COOKIE_STRING, X_XSRF_TOKEN, USER_AGENT, X_GIB_FGSSCGIB, X_GIB_GSSCGIB

logger = logging.getLogger(__name__)

class HHWebClient:
    """
    Парсер нового поколения (2026). 
    Снабжен сквозным принтованием и логированием для дебага тихих падений.
    """
    def __init__(self):
        print("\n[INIT] Инициализация HHWebClient...")
        logger.info("Инициализация HHWebClient")
        self.session = requests.Session()
        self.setup_session()

    def setup_session(self):
        """Конфигурирует сессию всеми необходимыми браузерными заголовками защиты"""
        print("[INIT] Настройка заголовков сессии и кук...")
        base_headers = {
            "accept": "application/json",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "user-agent": USER_AGENT,
            "x-requested-with": "XMLHttpRequest",
            "x-xsrftoken": X_XSRF_TOKEN,
            "x-gib-fgsscgib-w-hh": X_GIB_FGSSCGIB,
            "x-gib-gsscgib-w-hh": X_GIB_GSSCGIB,
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        self.session.headers.update(base_headers)
        self.session.headers.update({"cookie": RAW_COOKIE_STRING})
        print(f"[INIT] Сессия успешно настроена. Длина кук: {len(RAW_COOKIE_STRING)} симв.")

    def fetch_vacancies_page(self, page: int = 0) -> Dict[str, Any]:
        """
        ФАЗА 1: Поиск вакансий.
        Выводит в консоль точные данные перед выстрелом в сеть.
        """
        url = "https://hh.ru/shards/vacancy/search"
        
        print(f"\n🚀 === [ФАЗА 1] НАЧАЛО РАБОТЫ МЕТОДА fetch_vacancies_page (Страница: {page}) ===")
        
        complex_search_text = (
            'NAME:(QA OR AQA OR SDET OR "Quality Assurance" OR Тестировщик OR "тестированию" OR "обеспечению качества") '
            'NOT NAME:(Junior OR Trainee OR Стажер OR Младший OR 1C OR 1С OR Java OR Kotlin OR "Node.js" OR GameDev OR '
            'Нагрузочное OR Нагрузочный OR Performance OR Техник OR Сборщик OR Ассессор OR симулятор OR аппаратный OR радиоэлектронный OR '
            'сетевой OR языковой OR mobile OR мобильных)'
        )

        params = {
            "order_by": "publication_time",
            "ored_clusters": "true",
            "search_period": 1,
            "work_format": "REMOTE",
            "items_on_page": 20,
            "page": page,
            "search_field": ["name", "company_name", "description"],
            "enable_snippets": "false",
            "text": complex_search_text
        }

        self.session.headers.update({"referer": "https://hh.ru/search/vacancy"})
        
        print(f"[ФАЗА 1] Отправка GET запроса на URL: {url}")
        print(f"[ФАЗА 1] Параметры поиска: {params}")
        
        start_time = time.time()
        try:
            response = self.session.get(url, params=params, timeout=15)
            elapsed_time = time.time() - start_time
            
            print(f"[ФАЗА 1] Ответ получен за {elapsed_time:.2f} сек.")
            print(f"[ФАЗА 1] HTTP Статус-код: {response.status_code}")
            print(f"[ФАЗА 1] Реальный финальный URL запроса: {response.url}")
            
            if response.status_code != 200:
                print(f"❌ [ФАЗА 1] ОШИБКА СЕРВЕРА! Текст ответа (первые 500 симв): {response.text[:500]}")
                logger.error(f"Ошибка шарда поиска {response.status_code}: {response.text[:300]}")
            
            response.raise_for_status()
            
            raw_json = response.json()
            print(f"✅ [ФАЗА 1] УСПЕХ! JSON успешно декодирован. Длина ответа: {len(response.text)} симв.")
            
            # Проверяем структуру ответа во встроенном под-объекте
            search_result = raw_json.get("vacancySearchResult", {})
            vacancies_found = search_result.get("vacancies", [])
            print(f"[ФАЗА 1] Найдено вакансий на текущей странице: {len(vacancies_found)}")
            
            return raw_json
            
        except Exception as e:
            print(f"💥 [ФАЗА 1] КРИТИЧЕСКОЕ ИСКЛЮЧЕНИЕ ПРИ СЕТЕВОМ ЗАПРОСЕ: {e}")
            logger.error(f"Критическая ошибка Фазы 1: {e}")
            raise

    def fetch_vacancy_details(self, vacancy_id: str) -> dict:
        """
        ФАЗА 2: Скачивание и хирургический парсинг HTML-страницы вакансии.
        ФИКС ОШИБКИ 406: Явно подменяем Accept на text/html, так как запрашиваем веб-страницу.
        """
        url = f"https://hh.ru/vacancy/{vacancy_id}"
        print(f"\n📥 --- [ФАЗА 2] Парсинг карточки вакансии ID: {vacancy_id} ---")
        
        # Локально переопределяем заголовки конкретно для этого HTML-запроса
        headers_override = {
            # Говорим серверу, что теперь мы ждем обычную HTML верстку, как браузер
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "referer": f"https://hh.ru/vacancy/{vacancy_id}"
        }

        start_time = time.time()
        try:
            # Передаем headers_override. Requests объединит их с сессией, заместив 'accept'
            response = self.session.get(url, headers=headers_override, timeout=15)
            elapsed_time = time.time() - start_time
            
            print(f"[ФАЗА 2] Страница скачана за {elapsed_time:.2f} сек. Статус: {response.status_code}")
            response.raise_for_status()
            
            print(f"[ФАЗА 2] Запуск BeautifulSoup для ID {vacancy_id}...")
            soup = BeautifulSoup(response.text, "html.parser")
            
            desc_block = soup.find(attrs={"data-qa": "vacancy-description"})
            if desc_block:
                description_text = desc_block.get_text(separator="\n", strip=True)
                print(f"[ФАЗА 2] Блок описания найден! Размером {len(description_text)} символов.")
            else:
                print(f"⚠️ [ФАЗА 2] Внимание: Блок data-qa='vacancy-description' не найден. Применен запасной план.")
                description_text = soup.body.get_text(separator="\n", strip=True) if soup.body else ""

            skills_elements = soup.find_all(attrs={"data-qa": "skills-element"})
            key_skills = []
            for element in skills_elements:
                skill_text = element.get_text(strip=True)
                if skill_text:
                    key_skills.append(skill_text)
                    
            print(f"[ФАЗА 2] Успешно извлечено навыков: {len(key_skills)}")
            
            return {
                "id": vacancy_id,
                "description": description_text,
                "key_skills": key_skills
            }
            
        except Exception as e:
            print(f"💥 [ФАЗА 2] ИСКЛЮЧЕНИЕ при парсинге ID {vacancy_id}: {e}")
            logger.error(f"Не удалось спарсить HTML для вакансии {vacancy_id}: {e}")
            raise