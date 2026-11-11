"""Каталог: поиск свободных апартаментов по датам (на временной базе, боевые данные не трогаются)."""
import sqlite3
from datetime import date, timedelta

import pytest

from core import bookings_repo as repo
from core import catalog


@pytest.fixture
def env(tmp_path, monkeypatch):
    db_path = str(tmp_path / "t.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER, check_in TEXT, check_out TEXT, status TEXT)")
    conn.commit()
    conn.close()

    def fake_db():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        return c

    def add(prop, a, b, status="confirmed"):
        c = fake_db()
        c.execute("INSERT INTO bookings (property_id, check_in, check_out, status) VALUES (?,?,?,?)", (prop, a, b, status))
        c.commit()
        c.close()

    monkeypatch.setattr(repo, "get_db", fake_db)
    monkeypatch.setattr(catalog, "CATALOG_FILE", str(tmp_path / "catalog.json"))
    monkeypatch.setattr(catalog, "list_properties", lambda: [
        {"id": 1, "name": "Один", "address": "", "active": True, "slug": ""},
        {"id": 2, "name": "Два", "address": "", "active": True, "slug": "two"},
        {"id": 3, "name": "Три", "address": "", "active": False, "slug": "three"},
    ])
    return add


def _day(n):
    return (date.today() + timedelta(days=n)).isoformat()


def test_search_off_by_default(env):
    assert catalog.load_catalog_settings()["date_search"] is False
    with pytest.raises(catalog.CatalogError):
        catalog.catalog_availability(_day(5), _day(7))


def test_busy_and_free(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    env(1, _day(10), _day(14))
    env(2, _day(10), _day(14), status="cancelled")     # отменённая бронь не мешает
    env(3, _day(10), _day(14))                          # отключённый объект в ответ не попадает
    res = catalog.catalog_availability(_day(12), _day(13))
    assert res["busy"] == [1]


def test_checkout_day_is_free_for_next_checkin(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    env(1, _day(10), _day(14))
    assert catalog.catalog_availability(_day(14), _day(16))["busy"] == []
    assert catalog.catalog_availability(_day(8), _day(10))["busy"] == []
    assert catalog.catalog_availability(_day(13), _day(16))["busy"] == [1]


def test_blocks_count_as_busy(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    env(2, _day(20), _day(22), status="blocked")
    assert catalog.catalog_availability(_day(21), _day(23))["busy"] == [2]


def test_bad_dates(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    for a, b in ((_day(5), _day(5)), (_day(6), _day(5)), ("abc", _day(5)), (_day(-10), _day(-8)), (_day(1), _day(500))):
        with pytest.raises(catalog.CatalogError):
            catalog.catalog_availability(a, b)


def test_old_save_without_field_keeps_value(env):
    catalog.save_catalog_settings("", "", "", "", "", [], date_search=True)
    catalog.save_catalog_settings("Бренд", "", "", "", "", [])   # старый запрос без date_search
    assert catalog.load_catalog_settings()["date_search"] is True
    assert catalog.admin_catalog_state()["settings"]["date_search"] is True
    assert catalog.build_public_catalog()["date_search"] is True
