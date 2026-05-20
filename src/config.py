import os

# =====================================================================
# 🌐 НАСТРОЙКИ СЕССИИ БРАУЗЕРА ДЛЯ ВЕБ-ПАРСИНГА HH.RU
# =====================================================================
RAW_COOKIE_STRING = (
    "__ddg1_=HYExdqrHYqI4il1uKkep; hhuid=U7SBqt8HIE2652nd4kgx2w--; "
    "tmr_lvid=d121c3d24046c74d5168c3dfc64e4bfa; hhtoken=nkascu_uaitGAWzcYUJVxLttcUQa; "
    "_xsrf=b306848bf61418a8d00c9ed51445c8ca; hhrole=applicant; "
    "__zzatgib-w-hh=MDA0dC0jViV+FmELHw4/aQsbSl1pCENQGC9LX3QqPG0faEsXIkYQf3kmHhJ9JVhTOwxkQEZ2dF0+aB9nOVURCxIXRF5cVWl1FRpLSiVueCplJS0xViR8SylEXFQKJyEUf3AjUw0UVy8NPjteLW8PJwsSWAkhCklpC15zXV8WPkQhbAs4LBtFOA8teB1keEdXaygiEjRvVVgLPWFDQXIxMUBpH2ZQXiNLWgozWCIWfCUjVAw/X3J2Ky0bN1ddHBEkWA4hPwsXXFU+NVQOPHVXLw0uOF4tbx5mTmIhS1hVfiUdFwhnFRtQSxgvS18zWn4lDzRDS1sKFA4/VFFCQisVWVJ1KW59OjAbRVceZ0tgH0xXVX4XFXs/KGUaQE4nL0tfPm16L04efEsbNSEOPloLG3hyKlgJE15FRm13L0RhDysYIVQ1Xz9BYUpKPTdYH0t1MBI=+PVDeg==; "
    "fgsscgib-w-hh=zijFad8755e9c33e15aadd255cf75ce1d02c5bc3"
)
X_XSRF_TOKEN = "b306848bf61418a8d00c9ed51445c8ca"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
X_GIB_FGSSCGIB = "zijFad8755e9c33e15aadd255cf75ce1d02c5bc3"
X_GIB_GSSCGIB = "VJe01VWk7RI0WuWl/6KOAdWA1bfdsB8gDeXHpp8rN2EXD/2WPYlYePeJLdG55a21pL/gltqfTROT463DSR1jpMFy7ZErTaAfKb7RYXzVvyBvoxn2LyzhSIxp0QIY+lgCGw+ggaWLekT9ZO1LkAHyz3OGXwqxlUZdv1MRSgjY9Qo4dL6ICTV+kFy0fvBZn6lI0wZ6DCNBAtDUneR7MY8FpvRMpsOJRoGRMQzhw/wDeCjB8DN3cQtzgp/vdFCo2triNyEKYykRDFT7+RE="

# =====================================================================
# 🗄️ НАСТРОЙКИ БАЗЫ ДАННЫХ
# =====================================================================
DB_PATH = "vacancies.db"

# =====================================================================
# 🤖 НАСТРОЙКИ ИНТЕГРАЦИИ С ИИ
# =====================================================================
# 🟢 ИСПРАВЛЕНИЕ: Переводим значение в валидный для SDK v4+ формат "true"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_FALLBACK_KEY_HERE")