"""Установка на новом сервере: .env без лишнего, запуск без Telegram-токена, запрет индексации тестовой копии."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("raw, expected", [
    ("1008661058", [1008661058]),
    ("1, 2", [1, 2]),
    ("[1, -100500]", [1, -100500]),
    (" 7 8 ", [7, 8]),
    ("", []),
    (None, []),
    ("abc", []),
])
def test_parse_admin_ids(raw, expected):
    import config
    assert config.parse_admin_ids(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("https://example.ru", "https://example.ru"),
    ("https://example.ru/", "https://example.ru"),
    (' "https://example.ru/ " ', "https://example.ru"),
    ("", ""),
    (None, ""),
])
def test_clean_base_url(raw, expected):
    import config
    assert config.clean_base_url(raw) == expected


def test_config_has_no_hardcoded_site_values():
    """В config.py нет адреса сайта и Telegram-ID конкретного владельца: всё берётся из .env."""
    text = open(os.path.join(ROOT, "config.py"), encoding="utf-8").read()
    assert "citypause" not in text.lower()
    assert "1008661058" not in text


def test_runtime_imports_without_bot_token():
    """Без BOT_TOKEN модуль с ботом загружается (раньше приложение падало), бот помечен выключенным."""
    env = {k: v for k, v in os.environ.items() if k not in ("BOT_TOKEN",)}
    env["PYTHONPATH"] = ROOT
    code = "import core.runtime as r; print('ENABLED=' + str(r.BOT_ENABLED))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    # на сервере BOT_TOKEN может подтянуться из .env (load_dotenv), поэтому строгая проверка только без .env
    assert "ENABLED=False" in out.stdout or os.path.exists(os.path.join(ROOT, ".env")), out.stdout


def _noindex_app(monkeypatch, value):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.noindex import setup_noindex
    if value is None:
        monkeypatch.delenv("NOINDEX", raising=False)
    else:
        monkeypatch.setenv("NOINDEX", value)
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    setup_noindex(app)
    return TestClient(app)


def test_noindex_off_changes_nothing(monkeypatch):
    c = _noindex_app(monkeypatch, None)
    assert "x-robots-tag" not in c.get("/ping").headers
    assert c.get("/robots.txt").status_code == 404
    c = _noindex_app(monkeypatch, "0")
    assert c.get("/robots.txt").status_code == 404


def test_noindex_on_adds_robots_and_header(monkeypatch):
    c = _noindex_app(monkeypatch, "1")
    r = c.get("/ping")
    assert r.status_code == 200 and "noindex" in r.headers["x-robots-tag"]
    robots = c.get("/robots.txt")
    assert robots.status_code == 200 and "Disallow: /" in robots.text


def test_env_example_lists_required_keys_without_real_values():
    text = open(os.path.join(ROOT, "env.example"), encoding="utf-8").read()
    for key in ("BASE_URL=", "ADMIN_PASSWORD=", "SESSION_SECRET=", "MAIL_FROM=", "MAIL_PASSWORD=", "BACKUP_PASSWORD="):
        assert key in text
    assert "citypause" not in text.lower()


def test_polling_does_not_take_over_sigterm():
    """aiogram по умолчанию перехватывает SIGTERM у uvicorn: сервис не завершался и systemd убивал его через 90 секунд."""
    text = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "dp.start_polling(bot, handle_signals=False)" in text
