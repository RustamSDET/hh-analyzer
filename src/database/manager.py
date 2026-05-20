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
        """Создает таблицу vacancies, если её еще нет."""
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
            conn.commit()

    def save_discovered_ids(self, vacancy_ids: List[str]):
        """
        Шаг 1: Сохраняет только ID найденных вакансий со статусом 'NEW'.
        Если ID уже есть в базе, запрос его просто пропустит (INSERT OR IGNORE).
        """
        with self._get_connection() as conn:
            # Подготавливаем кортежи для массовой вставки
            data = [(v_id, "В процессе...", "NEW") for v_id in vacancy_ids]
            conn.executemany("""
                INSERT OR IGNORE INTO vacancies (id, name, status) 
                VALUES (?, ?, ?)
            """, data)
            conn.commit()

    def get_vacancies_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Возвращает список вакансий с определенным статусом (например, 'NEW' или 'PARSED')."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM vacancies WHERE status = ?", (status,))
            return [dict(row) for row in cursor.fetchall()]

    def update_vacancy_details(self, vacancy: VacancyDetails):
        """
        Шаг 2: Обновляет пустую вакансию скачанными деталями с HH 
        и переводит статус в 'PARSED'.
        """
        with self._get_connection() as conn:
            # Превращаем список навыков ['Python', 'Git'] в JSON-строку '["Python", "Git"]'
            skills_json = json.dumps(vacancy.key_skills, ensure_ascii=False)
            
            conn.execute("""
                UPDATE vacancies 
                SET name = ?, employer_name = ?, description = ?, alternate_url = ?, key_skills = ?, status = 'PARSED'
                WHERE id = ?
            """, (vacancy.name, vacancy.employer_name, vacancy.description, vacancy.alternate_url, skills_json, vacancy.id))
            conn.commit()

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

    def mark_as_failed(self, vacancy_id: str):
        """Если при парсинге или запросе к ИИ что-то пошло не так."""
        with self._get_connection() as conn:
            conn.execute("UPDATE vacancies SET status = 'FAILED' WHERE id = ?", (vacancy_id,))
            conn.commit()