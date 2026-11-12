"""Чат-помощник: вопросы и ответы по объектам (на временной папке, боевые данные не трогаются)."""
import json

import pytest

from core import chat_faq as cf


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, "CHAT_FAQ_FILE", str(tmp_path / "chat_faq.json"))
    monkeypatch.setattr(cf, "property_file", lambda legacy, pid=1: legacy if pid == 1 else str(tmp_path / f"p{pid}_chat.json"))
    return tmp_path


def test_default_is_off_with_empty_answers(env):
    s = cf.load_settings(1)
    assert s["enabled"] is False
    assert len(s["items"]) == len(cf.DEFAULT_QUESTIONS)
    assert all(i["answer"] == "" for i in s["items"])
    assert cf.public_view(1) == {"enabled": False}


def test_public_view_only_shows_enabled_visible_answered(env):
    cf.save_settings(1, {"enabled": True, "items": [
        {"id": "pets", "question": "Можно с животными?", "answer": "Нет."},
        {"id": "kids", "question": "Можно с детьми?", "answer": ""},                       # без ответа
        {"id": "smoking", "question": "Можно курить?", "answer": "Нет.", "visible": False},  # скрыт
    ]})
    pub = cf.public_view(1)
    assert pub["enabled"] is True
    assert [i["id"] for i in pub["items"]] == ["pets"]


def test_enabled_but_no_answers_stays_hidden(env):
    cf.save_settings(1, {"enabled": True, "items": [{"id": "pets", "question": "Q", "answer": ""}]})
    assert cf.public_view(1) == {"enabled": False}


def test_each_property_has_own_set(env):
    cf.save_settings(1, {"enabled": True, "items": [{"id": "a", "question": "Один?", "answer": "Первый"}]})
    cf.save_settings(2, {"enabled": True, "items": [{"id": "a", "question": "Два?", "answer": "Второй"}]})
    assert cf.public_view(1)["items"][0]["answer"] == "Первый"
    assert cf.public_view(2)["items"][0]["answer"] == "Второй"


def test_cleaning_limits_and_ids(env):
    s = cf.clean_settings({"title": "x" * 100, "greeting": "y" * 999, "items": [
        {"id": "dup", "question": "Один", "answer": "a" * 5000},
        {"id": "dup", "question": "Два"},                 # повторный номер заменяется новым
        {"id": "ПЛОХОЙ ID", "question": "Три"},           # некорректный номер заменяется новым
        {"id": "x", "question": "   "},                   # пустой вопрос отбрасывается
        "мусор",
    ] + [{"id": f"q{n}", "question": f"В{n}"} for n in range(60)]})
    assert len(s["title"]) == cf.TITLE_MAX and len(s["greeting"]) == cf.GREETING_MAX
    assert len(s["items"]) <= cf.MAX_ITEMS
    assert len(s["items"][0]["answer"]) == cf.ANSWER_MAX
    ids = [i["id"] for i in s["items"]]
    assert len(ids) == len(set(ids)) and ids[0] == "dup" and ids[1].startswith("c_") and ids[2].startswith("c_")


def test_broken_file_falls_back_to_default(env):
    (env / "chat_faq.json").write_text("{ не json", encoding="utf-8")
    assert cf.load_settings(1)["enabled"] is False


def test_html_is_stored_as_plain_text(env):
    cf.save_settings(1, {"enabled": True, "items": [{"id": "a", "question": "<b>Q</b>", "answer": "<script>alert(1)</script>"}]})
    raw = json.loads((env / "chat_faq.json").read_text(encoding="utf-8"))
    assert raw["items"][0]["answer"] == "<script>alert(1)</script>"   # хранится как текст; сайт выводит через textContent


def test_admin_view_has_hints_for_defaults(env):
    v = cf.admin_view(1)
    assert v["defaults"]["pets"]["example"] is True and v["defaults"]["cancel"]["example"] is False
    assert v["limits"]["answer"] == cf.ANSWER_MAX
