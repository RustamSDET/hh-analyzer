import os
import sys
import pytest

# Гарантируем, что корневая папка проекта находится в PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

@pytest.fixture
def db_session(tmp_path):
    """
    Фикстура для создания изолированной базы данных для каждого теста.
    Подменяет глобальный DB_PATH на временный файл, удаляющийся после завершения теста.
    """
    db_file = tmp_path / "test_vacancies.db"
    db_file_str = str(db_file)

    # Динамически переопределяем пути к БД в конфигах
    import src.config
    import src.database.manager

    orig_config_path = src.config.DB_PATH
    orig_manager_path = src.database.manager.DB_PATH

    src.config.DB_PATH = db_file_str
    src.database.manager.DB_PATH = db_file_str

    # Импортируем и инициализируем DBManager (он сам создаст таблицы и проведет миграции)
    from src.database.manager import DBManager
    manager = DBManager()

    yield manager

    # Восстанавливаем оригинальные пути
    src.config.DB_PATH = orig_config_path
    src.database.manager.DB_PATH = orig_manager_path

    # Закрываем все файловые дескрипторы и удаляем временный файл
    if db_file.exists():
        try:
            db_file.unlink()
        except OSError:
            pass

@pytest.fixture
def my_profile():
    """
    Возвращает текстовый профиль кандидата для проведения ИИ-скрининга.
    """
    return (
        "Опытный QA Automation Engineer / SDET.\n"
        "Ключевые навыки: Python, Pytest, Selenium, Playwright, Git, CI/CD, SQL, REST API, Docker.\n"
        "Предпочитаемый формат работы: Удаленка, возможность работы как ИП/B2B."
    )
