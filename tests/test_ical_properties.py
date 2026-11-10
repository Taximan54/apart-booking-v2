"""Календари площадок по объектам: у каждого объекта свои площадки и ссылки, брони и блокировки не смешиваются."""
import hashlib
from datetime import date

import pytest

import core.db as db
import core.ical_sync as sync
import core.properties as props
from core import bookings_repo as repo

TODAY = date(2027, 1, 1)
URL1 = "http://93.184.216.34/main.ics"      # адреса-числа, чтобы проверка ссылки не ходила в интернет
URL2 = "http://93.184.216.35/second.ics"


def ics(*events):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for uid, start, end in events:
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ICAL_FILE", str(tmp_path / "ical.json"))
    monkeypatch.setattr(props, "PROPERTIES_DIR", str(tmp_path / "properties"))
    reg = tmp_path / "properties.json"
    reg.write_text('[{"id":1,"name":"Основной","address":"","active":true,"slug":""},'
                   '{"id":2,"name":"Дом у Оперного","address":"","active":false,"slug":"opera"}]', encoding="utf-8")
    monkeypatch.setattr(props, "PROPERTIES_FILE", str(reg))
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "b.db"))
    return tmp_path


def setup_avito(pid, url):
    sync.add_platform("Авито", "avito", property_id=pid)
    sync.update_platform("avito", url=url, property_id=pid)


def blocks(pid, source="ical_avito"):
    return [b for b in repo.list_bookings(pid) if b["source"] == source and b["status"] == "blocked"]


def test_platforms_are_stored_per_property(env):
    setup_avito(1, URL1)
    setup_avito(2, URL2)
    assert [p["url"] for p in sync.list_platforms(1)] == [URL1]
    assert [p["url"] for p in sync.list_platforms(2)] == [URL2]
    t1 = sync.get_platform("avito", 1)["export_token"]
    t2 = sync.get_platform("avito", 2)["export_token"]
    assert t1 != t2
    assert (env / "ical.json").exists()                           # основной объект — прежний файл
    assert (env / "properties" / "2" / "ical.json").exists()       # второй — своя папка
    sync.add_platform("Суточно", "sutochno", property_id=2)
    assert [p["source"] for p in sync.list_platforms(1)] == ["avito"]   # у основного не появилось


def test_token_is_found_among_all_properties(env):
    setup_avito(1, URL1)
    setup_avito(2, URL2)
    t1 = sync.get_platform("avito", 1)["export_token"]
    t2 = sync.get_platform("avito", 2)["export_token"]
    assert sync.find_platform_by_token(t1)[0] == 1
    pid, platform = sync.find_platform_by_token(t2)
    assert pid == 2 and platform["export_token"] == t2
    assert sync.find_platform_by_token("nope") is None
    assert sync.platform_by_token(t1)["source"] == "avito"          # старая функция работает для основного объекта
    assert sync.platform_by_token(t2) is None


def test_sync_creates_blocks_only_in_own_property(env):
    setup_avito(2, URL2)
    rep = sync.sync_platform("avito", today=TODAY, fetch=lambda u: ics(("u1", "20270510", "20270513")), property_id=2)
    assert rep["ok"] and rep["created"] == 1
    assert len(blocks(2)) == 1 and blocks(1) == []
    assert blocks(2)[0]["check_in"] == "2027-05-10"
    assert sync.get_platform("avito", 2)["last_sync"]["ok"] and sync.get_platform("avito", 1) is None


def test_same_event_in_both_objects_gives_separate_blocks_and_main_ref_is_unchanged(env):
    setup_avito(1, URL1)
    setup_avito(2, URL2)
    feed = ics(("same-uid", "20270601", "20270604"))
    sync.sync_platform("avito", today=TODAY, fetch=lambda u: feed, property_id=1)
    sync.sync_platform("avito", today=TODAY, fetch=lambda u: feed, property_id=2)
    b1, b2 = blocks(1), blocks(2)
    assert len(b1) == 1 and len(b2) == 1
    assert b1[0]["username"] == "ICAL-" + hashlib.sha1(b"avito:same-uid").hexdigest()[:10].upper()   # формула основного объекта не изменилась
    assert b2[0]["username"] != b1[0]["username"]


def test_export_feed_contains_only_own_property(env):
    repo.insert_block(1, "BLOCK-A1", "2027-05-01", "2027-05-03", "x", 2)
    repo.insert_block(2, "BLOCK-B1", "2027-06-01", "2027-06-03", "y", 2)
    main = sync.build_export_feed("avito", today=TODAY)                   # без номера объекта — основной
    main_explicit = sync.build_export_feed("avito", today=TODAY, property_id=1)
    second = sync.build_export_feed("avito", today=TODAY, property_id=2)
    assert "BLOCK-A1" in main and "BLOCK-B1" not in main
    assert "BLOCK-A1" in main_explicit and "BLOCK-B1" not in main_explicit
    assert "BLOCK-B1" in second and "BLOCK-A1" not in second
    assert "Дом у Оперного" in second


def test_deleting_platform_of_one_property_keeps_other_blocks(env):
    setup_avito(1, URL1)
    setup_avito(2, URL2)
    feed = ics(("same-uid", "20270601", "20270604"))
    sync.sync_platform("avito", today=TODAY, fetch=lambda u: feed, property_id=1)
    sync.sync_platform("avito", today=TODAY, fetch=lambda u: feed, property_id=2)
    assert sync.delete_platform("avito", property_id=2) == 1
    assert blocks(2) == [] and len(blocks(1)) == 1
    assert sync.get_platform("avito", 1) is not None and sync.get_platform("avito", 2) is None


def test_repo_filters_by_property(env):
    repo.insert_external_block(1, "ICAL-111", "2027-05-01", "2027-05-03", 2, "ical_avito", "x")
    repo.insert_external_block(2, "ICAL-222", "2027-05-01", "2027-05-03", 2, "ical_avito", "x")
    assert len(repo.list_active_blocks("ical_avito", "2027-01-01")) == 2                  # без объекта — как раньше
    assert [b["username"] for b in repo.list_active_blocks("ical_avito", "2027-01-01", 2)] == ["ICAL-222"]
    assert repo.cancel_all_blocks("ical_avito", 2) == 1
    assert [b["username"] for b in repo.list_active_blocks("ical_avito", "2027-01-01")] == ["ICAL-111"]
    assert repo.cancel_all_blocks("ical_avito") == 1


def test_sync_all_properties_main_first_and_failure_does_not_stop_others(env):
    setup_avito(1, URL1)
    setup_avito(2, URL2)
    called = []

    def fetch(url):
        called.append(url)
        if url == URL1:
            raise sync.ICalError("площадка недоступна")
        return ics(("u2", "20270701", "20270703"))

    result = sync.sync_all_properties(today=TODAY, fetch=fetch)
    assert called == [URL1, URL2]                       # основной объект первым
    assert result[1]["avito"]["ok"] is False
    assert result[2]["avito"]["ok"] is True and len(blocks(2)) == 1
    assert sync.sync_all(today=TODAY, fetch=lambda u: ics()) .get("avito", {}).get("ok") is True   # старый вызов — только основной объект


def test_main_property_behaviour_without_property_argument(env):
    sync.add_platform("Авито", "avito")                 # как раньше, без номера объекта
    sync.update_platform("avito", url=URL1)
    rep = sync.sync_platform("avito", today=TODAY, fetch=lambda u: ics(("m1", "20270801", "20270803")))
    assert rep["ok"] and len(blocks(1)) == 1 and blocks(2) == []
    assert [p["source"] for p in sync.list_platforms()] == ["avito"]
