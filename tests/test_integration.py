import os
import json
import pytest
from unittest.mock import MagicMock, patch

# Хелпер для загрузки фикстур
def load_fixture(filename: str) -> str:
    filepath = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

# =====================================================================
# 1. ТЕСТ: Сбор новых вакансий, парсинг JSON поиска и запись в БД (NEW)
# =====================================================================
def test_search_and_save_to_db(db_session):
    """
    Проверяет, что при парсинге поисковой выдачи hh.ru сырые JSON-данные корректно 
    обрабатываются и 2 найденные вакансии сохраняются в базу данных в статусе 'NEW'.
    """
    from src.parser import HHWebClient

    search_json_str = load_fixture("hh_search.json")
    search_json_data = json.loads(search_json_str)

    client = HHWebClient()

    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = search_json_data
        mock_response.text = search_json_str
        mock_get.return_value = mock_response

        # Запускаем парсинг страницы поиска
        search_page = client.fetch_vacancies_page(page=0)
        search_result = search_page.get("vacancySearchResult", {})
        found_items = search_result.get("vacancies", [])

        # Сохраняем в изолированную тестовую базу данных
        db_session.save_discovered_vacancies(found_items)

    # Проверка записей в базе данных
    vacancies_in_db = db_session.get_vacancies_by_status("NEW")
    assert len(vacancies_in_db) == 2

    # Проверка первой вакансии
    v1 = next(v for v in vacancies_in_db if v["id"] == "999111")
    assert v1["name"] == "QA Automation Engineer"
    assert v1["employer_name"] == "Super Tech Corp"
    assert v1["alternate_url"] == "https://hh.ru/vacancy/999111"

    # Проверка второй вакансии
    v2 = next(v for v in vacancies_in_db if v["id"] == "999222")
    assert v2["name"] == "Senior SDET"
    assert v2["employer_name"] == "AI Innovations LLC"
    assert v2["alternate_url"] == "https://hh.ru/vacancy/999222"


# =====================================================================
# 2. ТЕСТ: Детальное скачивание HTML, парсинг разметки и обновление (PARSED)
# =====================================================================
def test_parse_details_and_save_to_db(db_session):
    """
    Проверяет, что при скачивании карточки вакансии HTML-разметка успешно парсится,
    извлекаются описание и навыки, после чего статус вакансии меняется на 'PARSED'.
    """
    from src.parser import HHWebClient

    # Сначала добавляем вакансию в статусе NEW в базу данных
    db_session.save_discovered_vacancies([{
        "vacancyId": "999111",
        "name": "QA Automation Engineer",
        "company": {"name": "Super Tech Corp"}
    }])

    html_content = load_fixture("hh_vacancy.html")
    client = HHWebClient()

    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Скачиваем и парсим карточку вакансии
        raw_details = client.fetch_vacancy_details("999111")
        
        # Обновляем детальную информацию в БД
        db_session.update_vacancy_details(
            vacancy_id="999111",
            description=raw_details.get("description", ""),
            key_skills=raw_details.get("key_skills", [])
        )

    # Проверка записей в базе данных
    parsed_vacancies = db_session.get_vacancies_by_status("PARSED")
    assert len(parsed_vacancies) == 1
    
    v = parsed_vacancies[0]
    assert v["id"] == "999111"
    assert "Мы ищем опытного QA Automation Engineer" in v["description"]
    assert "написание автотестов на Python" in v["description"]
    
    # Ключевые навыки в БД хранятся в формате JSON-строки
    skills = json.loads(v["key_skills"])
    assert skills == ["Python", "Pytest", "Selenium", "Git"]


# =====================================================================
# 3. ТЕСТ: Пакетный ИИ-анализ (Mock Gemini) и обновление (ANALYZED)
# =====================================================================
def test_ai_screening_and_save_to_db(db_session, my_profile):
    """
    Проверяет, что пакетный ИИ-анализ обрабатывает данные вакансий и сохраняет вердикт
    модели в структурированном виде, переводя запись в статус 'ANALYZED'.
    """
    from src.analyzer import run_vacancy_analysis_batch
    from src.analyzer.schemas import VacancyMatchingResult

    # Подготавливаем вакансию в статусе PARSED
    db_session.save_discovered_vacancies([{
        "vacancyId": "999111",
        "name": "QA Automation Engineer",
        "company": {"name": "Super Tech Corp"}
    }])
    db_session.update_vacancy_details(
        vacancy_id="999111",
        description="Требуется опытный специалист. Стек: Python, Pytest. Удаленная работа, прямое оформление ИП.",
        key_skills=["Python", "Pytest"]
    )

    parsed_vacancies = db_session.get_vacancies_by_status("PARSED")
    assert len(parsed_vacancies) == 1

    # Создаем ожидаемый результат анализа от ИИ под Pydantic схему
    mock_result = VacancyMatchingResult(
        score=5,
        ip_cooperation_chance="High",
        ip_analysis_reason="Вакансия напрямую предусматривает оформление контракта через ИП/B2B.",
        pros=["Полное соответствие стека", "Удаленный режим работы"],
        cons=["Не найдено минусов"],
        red_flags=[],
        summary="Идеальный мэтч с возможностью B2B сотрудничества."
    )

    # Мокаем пакетный вызов к ИИ
    with patch("src.analyzer.agent.analyzer_app.batch") as mock_batch:
        mock_batch.return_value = [{"result": mock_result}]

        # Запускаем скрининг
        batch_results = run_vacancy_analysis_batch(
            my_profile=my_profile,
            vacancies_data=parsed_vacancies,
            batch_size=10
        )

    # Эмулируем сохранение результатов из main.py в БД
    for v, ai_result in batch_results:
        v_id = v["id"]
        assert ai_result is not None
        
        details_dict = {
            "pros": ai_result.pros,
            "cons": ai_result.cons,
            "red_flags": ai_result.red_flags,
            "summary": ai_result.summary,
            "ip_analysis_reason": ai_result.ip_analysis_reason,
            "ip_cooperation_chance": ai_result.ip_cooperation_chance
        }
        
        db_session.update_ai_analysis(v_id, ai_result.score, json.dumps(details_dict, ensure_ascii=False))

    # Сверяем финальный статус в базе
    analyzed_vacancies = db_session.get_vacancies_by_status("ANALYZED")
    assert len(analyzed_vacancies) == 1
    
    v = analyzed_vacancies[0]
    assert v["id"] == "999111"
    assert v["ai_score"] == 5
    
    reasons = json.loads(v["ai_reasons"])
    assert reasons["ip_cooperation_chance"] == "High"
    assert reasons["summary"] == "Идеальный мэтч с возможностью B2B сотрудничества."
    assert "Полное соответствие стека" in reasons["pros"]


# =====================================================================
# 4. ТЕСТ: Крайний кейс А — Сетевой сбой во время поиска
# =====================================================================
def test_edge_case_search_http_error(db_session):
    """
    Проверяет, что при возникновении сетевых ошибок (например, HTTP 500) во время 
    глобального поиска, клиент выбрасывает контролируемое исключение, не повреждая БД.
    """
    from src.parser import HHWebClient
    import requests

    client = HHWebClient()

    with patch("requests.Session.get") as mock_get:
        # Симулируем ошибку подключения / падение сервера HeadHunter
        mock_get.side_effect = requests.exceptions.RequestException("HH Server is down!")

        with pytest.raises(requests.exceptions.RequestException):
            client.fetch_vacancies_page(page=0)

    # Проверяем, что в базу ничего не сохранилось и она осталась пустой
    stats = db_session.get_database_stats()
    assert sum(stats.values()) == 0


# =====================================================================
# 5. ТЕСТ: Крайний кейс Б — Отсутствие HTML-разметки описания
# =====================================================================
def test_edge_case_detail_missing_markup(db_session):
    """
    Проверяет резервный сценарий парсинга деталей, когда на странице отсутствует блок 
    data-qa="vacancy-description". Парсер должен спарсить текст со всего body.
    """
    from src.parser import HHWebClient

    db_session.save_discovered_vacancies([{
        "vacancyId": "999333",
        "name": "Junior Developer",
        "company": {"name": "Test Company"}
    }])

    client = HHWebClient()
    
    # HTML полностью без блоков data-qa
    missing_markup_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Broken Layout</title>
    </head>
    <body>
        Это произвольный текст тела вакансии без специального тега описания.
        Но здесь все равно написаны полезные требования к вакансии.
    </body>
    </html>
    """

    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = missing_markup_html
        mock_get.return_value = mock_response

        raw_details = client.fetch_vacancy_details("999333")
        
        db_session.update_vacancy_details(
            vacancy_id="999333",
            description=raw_details.get("description", ""),
            key_skills=raw_details.get("key_skills", [])
        )

    # Проверяем базу
    parsed_vacancies = db_session.get_vacancies_by_status("PARSED")
    assert len(parsed_vacancies) == 1
    
    v = parsed_vacancies[0]
    assert v["id"] == "999333"
    # Текст из body должен быть успешно извлечен
    assert "Это произвольный текст тела вакансии без специального тега описания." in v["description"]
    assert "Но здесь все равно написаны полезные требования" in v["description"]
    
    # Навыков нет, так как теги key-skills также отсутствуют
    skills = json.loads(v["key_skills"])
    assert len(skills) == 0


# =====================================================================
# 6. ТЕСТ: Крайний кейс В — Сбой ИИ внутри батча (concurrency)
# =====================================================================
def test_edge_case_gemini_batch_exceptions(db_session, my_profile):
    """
    Проверяет, что если одна из вакансий в пакете падает с ошибкой ИИ (например, таймаут или 
    лимиты запросов к Gemini), весь батч не завершается аварийно. Успешные вакансии переводятся 
    в 'ANALYZED', а сбойная — в статус 'FAILED'.
    """
    from src.analyzer import run_vacancy_analysis_batch
    from src.analyzer.schemas import VacancyMatchingResult

    # Добавляем 3 вакансии в статусе PARSED
    db_session.save_discovered_vacancies([
        {"vacancyId": "101", "name": "AQA Python", "company": {"name": "Company A"}},
        {"vacancyId": "102", "name": "SDET Lead", "company": {"name": "Company B"}},
        {"vacancyId": "103", "name": "QA Manual", "company": {"name": "Company C"}}
    ])
    for vid in ["101", "102", "103"]:
        db_session.update_vacancy_details(vid, f"Описание вакансии {vid}", ["Git"])

    parsed_vacancies = db_session.get_vacancies_by_status("PARSED")
    assert len(parsed_vacancies) == 3

    # Готовим mock ИИ-результаты
    mock_res1 = VacancyMatchingResult(
        score=4, ip_cooperation_chance="Medium", ip_analysis_reason="Ok",
        pros=["Pro1"], cons=[], red_flags=[], summary="S1"
    )
    mock_res3 = VacancyMatchingResult(
        score=5, ip_cooperation_chance="High", ip_analysis_reason="Great",
        pros=["Pro3"], cons=[], red_flags=[], summary="S3"
    )

    # 1-я вакансия успешна, 2-я падает с исключением (как вернет LangGraph.batch с return_exceptions=True),
    # 3-я вакансия успешна
    mock_batch_outputs = [
        {"result": mock_res1},
        ValueError("Gemini Rate Limit Exceeded or API Quota Error"),
        {"result": mock_res3}
    ]

    with patch("src.analyzer.agent.analyzer_app.batch") as mock_batch:
        mock_batch.return_value = mock_batch_outputs

        # Запускаем батч-анализ
        batch_results = run_vacancy_analysis_batch(
            my_profile=my_profile,
            vacancies_data=parsed_vacancies,
            batch_size=10
        )

    # Проверяем структуру возвращаемого значения
    assert len(batch_results) == 3
    assert batch_results[0][1] == mock_res1
    assert batch_results[1][1] is None  # Успешно обработано исключение, вернув None
    assert batch_results[2][1] == mock_res3

    # Сохраняем результаты в базу данных (повторяем логику main.py)
    for v, ai_result in batch_results:
        v_id = v["id"]
        if ai_result is None:
            db_session.mark_as_failed(v_id)
            continue

        details_dict = {
            "pros": ai_result.pros,
            "cons": ai_result.cons,
            "red_flags": ai_result.red_flags,
            "summary": ai_result.summary,
            "ip_analysis_reason": ai_result.ip_analysis_reason,
            "ip_cooperation_chance": ai_result.ip_cooperation_chance
        }
        db_session.update_ai_analysis(v_id, ai_result.score, json.dumps(details_dict, ensure_ascii=False))

    # Сверяем финальное состояние вакансий в базе
    
    # 101 и 103 должны стать ANALYZED
    analyzed = db_session.get_vacancies_by_status("ANALYZED")
    assert len(analyzed) == 2
    analyzed_ids = {row["id"] for row in analyzed}
    assert "101" in analyzed_ids
    assert "103" in analyzed_ids

    # 102 должна стать FAILED
    failed = db_session.get_vacancies_by_status("FAILED")
    assert len(failed) == 1
    assert failed[0]["id"] == "102"
