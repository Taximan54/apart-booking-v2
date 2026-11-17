"""Запрет индексации сайта поисковиками (для тестовых копий): включается строкой NOINDEX=1 в .env."""
import os

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


def noindex_enabled() -> bool:
    return os.getenv("NOINDEX", "").strip().lower() in ("1", "true", "yes", "on")


def setup_noindex(app: FastAPI) -> bool:
    """Если NOINDEX включён: отдаёт /robots.txt с запретом и добавляет X-Robots-Tag ко всем ответам. Иначе ничего не меняет."""
    if not noindex_enabled():
        return False

    @app.middleware("http")
    async def _add_noindex_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.get("/robots.txt", include_in_schema=False)
    async def _robots():
        return PlainTextResponse("User-agent: *\nDisallow: /\n")

    return True
