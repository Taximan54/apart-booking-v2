"""Минимальный срок бронирования по объектам (на временной папке, боевые данные не трогаются)."""
import os
import sqlite3
from datetime import date, timedelta

import pytest

from core import booking_rules as br
from core import bookings_repo as repo
from core import catalog


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "BOOKING_RULES_FILE", str(tmp_path / "booking_rules.json"))
    monkeypatch.setattr(br, "property_file", lambda legacy, pid=1: legacy if pid == 1 else str(tmp_path / f"p{pid}_rules.json"))
    db = str(tmp_path / "t.db")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER, check_in TEXT, check_out TEXT, status TEXT)")
    c.commit(); c.close()
    def fake_db():
        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row; return conn
    monkeypatch.setattr(repo, "get_db", fake_db)
    monkeypatch.setattr(catalog, "CATALOG_FILE", str(tmp_path / "catalog.json"))
    monkeypatch.setattr(catalog, "list_properties", lambda: [
        {"id": 1, "name": "Один", "address": "", "active": True, "slug": ""},
        {"id": 2, "name": "Два", "address": "", "active": True, "slug": "two"}])
    monkeypatch.setattr(catalog, "get_min_nights", br.get_min_nights)
    return tmp_path


def _day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def test_default_is_two_nights(env):
    assert br.get_min_nights(1) == 2 and br.get_min_nights(2) == 2


def test_each_property_has_its_own_value(env):
    br.set_min_nights(1, 1)
    br.set_min_nights(2, 3)
    assert br.get_min_nights(1) == 1 and br.get_min_nights(2) == 3


def test_value_is_clamped(env):
    assert br.set_min_nights(1, 0) == 1
    assert br.set_min_nights(1, 999) == 30
    assert br.clean_min_nights("abc") == 2


def test_broken_file_falls_back_to_default(env):
    (env / "booking_rules.json").write_text("{ не json", encoding="utf-8")
    assert br.get_min_nights(1) == 2


def test_ru_nights():
    assert [br.ru_nights(n) for n in (1, 2, 5, 11, 21, 22)] == ["1 ночь", "2 ночи", "5 ночей", "11 ночей", "21 ночь", "22 ночи"]


def test_catalog_marks_too_short_per_property(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    br.set_min_nights(1, 1)
    br.set_min_nights(2, 3)
    res = catalog.catalog_availability(_day(10), _day(11))      # 1 ночь
    assert res["too_short"] == {"2": 3}
    res = catalog.catalog_availability(_day(10), _day(13))      # 3 ночи подходят обоим
    assert res["too_short"] == {}
