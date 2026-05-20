import re
import html

def clean_html(raw_html: str) -> str:
    """
    Очищает текст от HTML-тегов HeadHunter и декодирует спецсимволы.
    Пример: '<p>Привет &amp; пока</p>' -> 'Привет & пока'
    """
    if not raw_html:
        return ""
    
    # 1. Удаляем все HTML теги (заменяем на пробел, чтобы слова не слипались)
    clean_text = re.sub(r'<[^>]+>', ' ', raw_html)
    
    # 2. Декодируем сущности типа &amp;, &nbsp;, &lt;, &gt; в нормальные символы
    clean_text = html.unescape(clean_text)
    
    # 3. Схлопываем множественные пробелы и переносы строк в один пробел
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    return clean_text.strip()