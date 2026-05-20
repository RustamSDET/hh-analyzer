import sqlite3
import json
from typing import List, Optional, Dict, Any
from src.config import DB_PATH
from src.parser.schemas import VacancyDetails

class DBManager:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _get_connection(self):
        """Создает подключение к SQLite. Позволяет обращаться к колонкам по именам."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Создает таблицу vacancies и автоматически проводит миграции новых колонок."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    employer_name TEXT,
                    description TEXT,
                    alternate_url TEXT,
                    key_skills TEXT,
                    status TEXT DEFAULT 'NEW',
                    ai_score INTEGER,
                    ai_reasons TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 🟢 АВТО-МИГРАЦИЯ: Безопасно добавляем колонку user_status, если её ещё нет в базе
            try:
                conn.execute("ALTER TABLE vacancies ADD COLUMN user_status TEXT DEFAULT 'CONSIDERING'")
                print("[DB] Миграция успешна: добавлена колонка user_status.")
            except sqlite3.OperationalError:
                # Колонка уже существует, игнорируем ошибку
                pass
                
            conn.commit()

    def save_discovered_vacancies(self, vacancies: List[dict]):
        """
        Шаг 1: Принимает сырые объекты вакансий из веб-выдачи.
        Сохраняет ID, имя, компанию и ссылку. Если дубликат - игнорирует.
        """
        with self._get_connection() as conn:
            data = []
            for v in vacancies:
                v_id = str(v.get("vacancyId", ""))
                if not v_id:
                    continue
                name = v.get("name", "Не указано")
                company_dict = v.get("company") or {}
                employer_name = company_dict.get("name", "Не указан")
                url = f"https://hh.ru/vacancy/{v_id}"
                
                data.append((v_id, name, employer_name, url, "NEW"))

            conn.executemany("""
                INSERT OR IGNORE INTO vacancies (id, name, employer_name, alternate_url, status) 
                VALUES (?, ?, ?, ?, ?)
            """, data)
            conn.commit()

    def update_vacancy_details(self, vacancy_id: str, description: str, key_skills: List[str]):
        """
        Шаг 2: Дописывает в базу скачанное HTML-описание и навыки,
        не затирая имя и компанию, сохраненные на Шаге 1.
        """
        with self._get_connection() as conn:
            skills_json = json.dumps(key_skills, ensure_ascii=False)
            conn.execute("""
                UPDATE vacancies 
                SET description = ?, key_skills = ?, status = 'PARSED'
                WHERE id = ?
            """, (description, skills_json, vacancy_id))
            conn.commit()

    def get_vacancies_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Возвращает список вакансий с определенным статусом (например, 'NEW' или 'PARSED')."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM vacancies WHERE status = ?", (status,))
            return [dict(row) for row in cursor.fetchall()]

    def update_ai_analysis(self, vacancy_id: str, score: int, reasons: str):
        """
        Шаг 3: Записывает вердикт от ИИ и переводит статус в 'ANALYZED'.
        """
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE vacancies 
                SET ai_score = ?, ai_reasons = ?, status = 'ANALYZED'
                WHERE id = ?
            """, (score, reasons, vacancy_id))
            conn.commit()

    def update_user_status(self, vacancy_id: str, user_status: str):
        """
        🟢 БИЗНЕС-ВОРОНКА: Обновляет статус взаимодействия соискателя с вакансией
        Допустимые значения: CONSIDERING (по умолч.), APPLIED (Откликнулся), REJECTED (Скрыл)
        """
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE vacancies 
                SET user_status = ?
                WHERE id = ?
            """, (user_status, vacancy_id))
            conn.commit()

    def mark_as_failed(self, vacancy_id: str):
        """Если при парсинге или запросе к ИИ что-то пошло не так."""
        with self._get_connection() as conn:
            conn.execute("UPDATE vacancies SET status = 'FAILED' WHERE id = ?", (vacancy_id,))
            conn.commit()