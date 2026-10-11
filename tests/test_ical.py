"""Синхронизация календаря с Авито (iCal): разбор, сборка, безопасность ссылок, импорт и экспорт."""
import asyncio
import socket
import sqlite3
from datetime import date, datetime

import pytest

from core import ical
from core.ical import ICalError, build_ical, check_calendar_url, parse_ical

TODAY = date(2026, 10, 10)

AVITO_FEED = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Avito//RU\r\n"
    "BEGIN:VEVENT\r\nUID:avito-1\r\nDTSTART;VALUE=DATE:20261101\r\nDTEND;VALUE=DATE:20261104\r\nSUMMARY:Бронь\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nUID:avito-2\r\nDTSTART;VALUE=DATE:20261120\r\nDTEND;VALUE=DATE:20261122\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def feed(*events):
    """Собирает календарь из пар (uid, 'YYYYMMDD', 'YYYYMMDD')."""
    body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    for uid, a, b in events:
        body += f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART;VALUE=DATE:{a}\r\nDTEND;VALUE=DATE:{b}\r\nEND:VEVENT\r\n"
    return body + "END:VCALENDAR\r\n"


# ---------------------------------------------------------------------------
# Разбор и сборка
# ---------------------------------------------------------------------------

def test_parse_date_events_and_defaults():
    events = parse_ical(AVITO_FEED)
    assert [(e["uid"], e["start"], e["end"]) for e in events] == [
        ("avito-1", date(2026, 11, 1), date(2026, 11, 4)),
        ("avito-2", date(2026, 11, 20), date(2026, 11, 22)),
    ]
    assert events[0]["summary"] == "Бронь" and not events[0]["cancelled"]


def test_parse_datetime_folded_lines_cancelled_and_missing_end():
    text = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART:20261105T140000Z\nDTEND:20261107T110000Z\n"
        "SUMMARY:Длинное описание\n  продолжение\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:b\nDTSTART;VALUE=DATE:20261201\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:c\nDTSTART;VALUE=DATE:20261210\nDTEND;VALUE=DATE:20261212\nSTATUS:CANCELLED\nEND:VEVENT\n"
        "BEGIN:VEVENT\nUID:broken\nDTSTART:не-дата\nEND:VEVENT\n"
        "END:VCALENDAR\n"
    )
    events = {e["uid"]: e for e in parse_ical(text)}
    assert set(events) == {"a", "b", "c"}                      # битое событие пропущено
    assert (events["a"]["start"], events["a"]["end"]) == (date(2026, 11, 5), date(2026, 11, 7))
    assert events["a"]["summary"] == "Длинное описание продолжение"
    assert events["b"]["end"] == date(2026, 12, 2)             # без DTEND — одна ночь
    assert events["c"]["cancelled"] is True


def test_parse_rejects_non_calendar():
    with pytest.raises(ICalError):
        parse_ical("<html>Not a calendar</html>")


def test_build_ical_format_and_no_personal_data():
    events = [{"uid": "GP-AAA111@example.ru", "start": date(2026, 11, 1), "end": date(2026, 11, 3), "summary": "Занято"}]
    text = build_ical(events, calendar_name="Длинное-название, с запятой; и точкой " * 3, now=datetime(2026, 10, 1, 12, 0))
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    for raw in text.split("\r\n"):
        assert len(raw.encode("utf-8")) <= 75, f"строка длиннее 75 байт: {raw!r}"
    assert "DTSTART;VALUE=DATE:20261101" in text and "DTEND;VALUE=DATE:20261103" in text
    assert "UID:GP-AAA111@example.ru" in text and "DTSTAMP:20261001T120000Z" in text
    back = parse_ical(text)
    assert [(e["uid"], e["start"], e["end"]) for e in back] == [("GP-AAA111@example.ru", date(2026, 11, 1), date(2026, 11, 3))]


# ---------------------------------------------------------------------------
# Безопасность ссылок
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "ftp://example.com/cal.ics", "file:///etc/passwd", "javascript:alert(1)", "http://localhost/cal.ics",
    "http://127.0.0.1/cal.ics", "http://10.0.0.5/cal.ics", "http://192.168.1.1/cal.ics", "http://169.254.169.254/latest",
    "http://[::1]/cal.ics", "https://printer.local/cal.ics", "", "не ссылка", "https://" + "a" * 700 + ".ru",
])
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(ICalError):
        check_calendar_url(url, resolve=False)


def test_public_url_is_accepted_and_dns_to_private_is_rejected(monkeypatch):
    assert check_calendar_url(" https://8.8.8.8/cal.ics ", resolve=False) == "https://8.8.8.8/cal.ics"
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))])
    assert check_calendar_url("https://calendar.example.com/x.ics") == "https://calendar.example.com/x.ics"
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("10.1.2.3", 443))])
    with pytest.raises(ICalError):
        check_calendar_url("https://evil.example.com/x.ics")           # имя ведёт на внутренний адрес
    def no_dns(*a, **k):
        raise OSError("no dns")
    monkeypatch.setattr(ical.socket, "getaddrinfo", no_dns)
    with pytest.raises(ICalError):
        check_calendar_url("https://nonexistent.example.com/x.ics")


# ---------------------------------------------------------------------------
# Площадки, импорт и экспорт на настоящей базе
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    import core.db as database
    import core.ical_sync as sync
    path = str(tmp_path / "bookings.db")
    monkeypatch.setattr(database, "DB_FILE", path)
    monkeypatch.setattr(sync, "ICAL_FILE", str(tmp_path / "ical.json"))
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER DEFAULT 1, "
        "user_id INTEGER DEFAULT 0, username TEXT, check_in TEXT, check_out TEXT, guests INTEGER DEFAULT 2, "
        "status TEXT DEFAULT 'waiting_payment', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(ical.socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", 443))])
    return sync, path


@pytest.fixture
def avito(env):
    sync, path = env
    sync.add_platform("Авито", "avito")
    sync.update_platform("avito", url="https://avito.example.com/calendar/abc.ics")
    return sync, path


def rows(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    result = [dict(r) for r in conn.execute("SELECT * FROM bookings ORDER BY id")]
    conn.close()
    return result


def run_sync(sync, text, source="avito"):
    return sync.sync_platform(source, today=TODAY, fetch=lambda url: text)


# --- список площадок ---------------------------------------------------------

def test_add_platform_validation(env):
    sync, _ = env
    p = sync.add_platform("  Яндекс   Путешествия ", "yandex")
    assert p["name"] == "Яндекс Путешествия" and p["source"] == "yandex" and p["enabled"] and p["url"] == ""
    assert len(p["export_token"]) >= 24
    auto = sync.add_platform("Моя площадка")                                  # код создаётся сам
    assert auto["source"].startswith("x") and len(auto["source"]) == 9
    for name, source, message in [
        ("", "", "название"), ("x" * 61, "", "длинное"),
        ("Дубль", "yandex", "уже добавлена"), ("Резерв", "phone", "зарезервирован"),
        ("Плохой", "Bad Code!", "латиница"), ("Плохой", "ical_avito", "латиница"), ("Плохой", "a", "латиница"),
    ]:
        with pytest.raises(sync.IntegrationError, match=message):
            sync.add_platform(name, source)


def test_platform_limit_is_enough_for_many_services(env):
    sync, _ = env
    for i in range(sync.MAX_PLATFORMS):
        sync.add_platform(f"Площадка {i}")
    assert len(sync.list_platforms()) == 30
    with pytest.raises(sync.IntegrationError, match="не больше"):
        sync.add_platform("Лишняя")


def test_update_and_delete_platform(env):
    sync, path = env
    sync.add_platform("Авито", "avito")
    sync.update_platform("avito", name=" Avito.ru ", url=" https://avito.example.com/c.ics ", enabled=False)
    p = sync.get_platform("avito")
    assert (p["name"], p["url"], p["enabled"]) == ("Avito.ru", "https://avito.example.com/c.ics", False)
    with pytest.raises(sync.IntegrationError):
        sync.update_platform("avito", url="http://127.0.0.1/c.ics")           # внутренний адрес нельзя
    with pytest.raises(sync.IntegrationError):
        sync.update_platform("nope", name="x")
    sync.update_platform("avito", enabled=True)
    run_sync(sync, AVITO_FEED)
    assert len(rows(path)) == 2
    assert sync.delete_platform("avito") == 2                                  # блокировки площадки сняты
    assert sync.list_platforms() == [] and all(b["status"] == "cancelled" for b in rows(path))
    with pytest.raises(sync.IntegrationError):
        sync.delete_platform("avito")


# --- импорт --------------------------------------------------------------------

def test_sync_creates_blocks_and_is_idempotent(avito):
    sync, path = avito
    r1 = run_sync(sync, AVITO_FEED)
    assert r1["ok"] and (r1["created"], r1["updated"], r1["cancelled"]) == (2, 0, 0)
    data = rows(path)
    assert len(data) == 2 and all(b["status"] == "blocked" and b["source"] == "ical_avito" for b in data)
    assert (data[0]["check_in"], data[0]["check_out"], data[0]["nights"]) == ("2026-11-01", "2026-11-04", 3)
    assert data[0]["username"].startswith("ICAL-") and data[0]["guest_name"].startswith("Авито")
    r2 = run_sync(sync, AVITO_FEED)
    assert (r2["created"], r2["updated"], r2["cancelled"]) == (0, 0, 0) and len(rows(path)) == 2
    assert sync.get_platform("avito")["last_sync"]["ok"] is True


def test_sync_updates_changed_dates_and_cancels_removed(avito):
    sync, path = avito
    run_sync(sync, AVITO_FEED)
    r = run_sync(sync, feed(("avito-1", "20261102", "20261105")))             # avito-2 пропал, avito-1 сдвинулся
    assert (r["created"], r["updated"], r["cancelled"]) == (0, 1, 1)
    statuses = sorted((b["status"], b["check_in"]) for b in rows(path))
    assert statuses == [("blocked", "2026-11-02"), ("cancelled", "2026-11-20")]
    r = run_sync(sync, AVITO_FEED)                                             # бронь вернулась -> блокировка снова действует
    assert (r["created"], r["updated"]) == (0, 2) and all(b["status"] == "blocked" for b in rows(path))


def test_sync_ignores_past_and_cancelled_events(avito):
    sync, path = avito
    text = feed(("old", "20260901", "20260905"), ("ok", "20261201", "20261203"))
    text = text.replace("END:VCALENDAR", "BEGIN:VEVENT\r\nUID:c\r\nDTSTART;VALUE=DATE:20261215\r\nDTEND;VALUE=DATE:20261217\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\nEND:VCALENDAR")
    r = run_sync(sync, text)
    assert r["created"] == 1 and [b["check_in"] for b in rows(path)] == ["2026-12-01"]


def test_sync_skips_dates_already_covered_by_our_bookings(avito):
    sync, path = avito
    from core import bookings_repo as repo
    pid = sync.DEFAULT_PROPERTY_ID
    repo.insert_website_booking(pid, "GP-AAA111", "2026-11-01", "2026-11-04", 2, "Иван", "+7", "a@b.c", "", "", "tbank", 9000, 3, "", 0)
    repo.insert_manual_booking(pid, "GP-AVI222", "2026-11-20", "2026-11-22", 2, "", "", "", "", "", 5000, 2, "avito", 0, "tok")
    r = run_sync(sync, AVITO_FEED)
    assert (r["created"], r["skipped"]) == (0, 2) and len(rows(path)) == 2


def test_partial_overlap_still_creates_block_for_safety(avito):
    sync, path = avito
    from core import bookings_repo as repo
    repo.insert_website_booking(sync.DEFAULT_PROPERTY_ID, "GP-AAA111", "2026-11-02", "2026-11-03", 2, "Иван", "+7", "a@b.c", "", "", "tbank", 3000, 1, "", 0)
    r = run_sync(sync, feed(("avito-1", "20261101", "20261104")))
    assert r["created"] == 1 and r["skipped"] == 0     # площадка занята шире нашей брони: даты должны быть закрыты


def test_existing_block_is_cancelled_when_we_take_the_same_dates(avito):
    sync, path = avito
    from core import bookings_repo as repo
    run_sync(sync, feed(("avito-1", "20261101", "20261104")))
    repo.insert_manual_booking(sync.DEFAULT_PROPERTY_ID, "GP-MAN111", "2026-11-01", "2026-11-04", 2, "", "", "", "", "", 5000, 3, "phone", 0, "t")
    r = run_sync(sync, feed(("avito-1", "20261101", "20261104")))
    assert r["cancelled"] == 1 and sorted(b["status"] for b in rows(path)) == ["cancelled", "confirmed"]


def test_failures_change_nothing(avito):
    sync, path = avito
    run_sync(sync, AVITO_FEED)
    before = rows(path)

    def broken(url):
        raise ICalError("Не удалось скачать календарь: timeout")
    r = sync.sync_platform("avito", today=TODAY, fetch=broken)
    assert r["ok"] is False and "timeout" in r["error"]
    r = run_sync(sync, "<html>captcha</html>")
    assert r["ok"] is False and "iCal" in r["error"]
    assert rows(path) == before, "при ошибке брони трогать нельзя"
    assert sync.get_platform("avito")["last_sync"]["ok"] is False


def test_sync_without_url_or_unknown_platform_does_nothing(env):
    sync, path = env
    sync.add_platform("Авито", "avito")
    r = run_sync(sync, AVITO_FEED)
    assert r["ok"] is False and "не указана" in r["error"] and rows(path) == []
    assert run_sync(sync, AVITO_FEED, source="nope")["error"] == "Площадка не найдена"


# --- несколько площадок --------------------------------------------------------

@pytest.fixture
def three(env):
    sync, path = env
    for source, name in (("avito", "Авито"), ("yandex", "Яндекс Путешествия"), ("sutochno", "Суточно.ру")):
        sync.add_platform(name, source)
        sync.update_platform(source, url=f"https://{source}.example.com/cal.ics")
    return sync, path


def test_each_platform_gets_what_the_others_have_but_not_its_own(three):
    sync, path = three
    from core import bookings_repo as repo
    pid = sync.DEFAULT_PROPERTY_ID
    repo.insert_website_booking(pid, "GP-WEB111", "2026-11-10", "2026-11-12", 2, "Секретный Гость", "+7999", "x@y.z", "", "1234 567890", "tbank", 9000, 2, "", 0)
    repo.insert_manual_booking(pid, "GP-AVI222", "2026-11-15", "2026-11-17", 2, "Гость Авито", "", "", "", "", 5000, 2, "avito", 0, "t1")
    repo.insert_manual_booking(pid, "GP-YND333", "2026-11-20", "2026-11-22", 2, "Гость Яндекса", "", "", "", "", 5000, 2, "yandex", 0, "t2")
    repo.insert_block(pid, "BLOCK-444444", "2026-12-01", "2026-12-03", "ремонт", 2)
    repo.insert_website_booking(pid, "GP-CAN555", "2026-12-10", "2026-12-12", 2, "Отменён", "+7", "c@c.c", "", "", "tbank", 1, 2, "", 0)
    repo.set_status_by_ref("GP-CAN555", "cancelled")
    repo.insert_website_booking(pid, "GP-OLD666", "2026-09-01", "2026-09-03", 2, "Старый", "+7", "o@o.o", "", "", "tbank", 1, 2, "", 0)
    run_sync(sync, feed(("s1", "20261225", "20261228")), source="sutochno")      # блокировка из календаря Суточно
    run_sync(sync, feed(("a1", "20270105", "20270107")), source="avito")         # блокировка из календаря Авито

    def uids(source):
        return sorted(e["uid"].split("@")[0] for e in parse_ical(sync.build_export_feed(source, today=TODAY)))

    ical_ids = {b["username"]: b for b in rows(path) if b["source"].startswith("ical_")}
    sutochno_ref = next(r for r, b in ical_ids.items() if b["source"] == "ical_sutochno")
    avito_ref = next(r for r, b in ical_ids.items() if b["source"] == "ical_avito")
    common = ["BLOCK-444444", "GP-WEB111"]
    # Авито видит всё, кроме своих броней и своих блокировок
    assert uids("avito") == sorted(common + ["GP-YND333", sutochno_ref])
    # Яндекс не получает свои брони, но получает брони Авито и блокировки Суточно
    assert uids("yandex") == sorted(common + ["GP-AVI222", sutochno_ref, avito_ref])
    # Суточно не получает свои блокировки
    assert uids("sutochno") == sorted(common + ["GP-AVI222", "GP-YND333", avito_ref])
    text = sync.build_export_feed("yandex", today=TODAY)
    for secret in ("Секретный Гость", "Гость Авито", "Гость Яндекса", "1234 567890", "+7999", "x@y.z", "ремонт"):
        assert secret not in text, f"в календаре не должно быть: {secret}"


def test_echo_of_other_platform_booking_is_not_duplicated(three):
    sync, path = three
    run_sync(sync, feed(("y1", "20261101", "20261104")), source="yandex")        # бронь на Яндексе -> блокировка у нас
    # мы отдали её Авито, и Авито вернул её нам как свою: блокировка не должна дублироваться
    r = run_sync(sync, feed(("echo", "20261101", "20261104")), source="avito")
    assert (r["created"], r["skipped"]) == (0, 1)
    assert sorted((b["source"], b["status"]) for b in rows(path)) == [("ical_yandex", "blocked")]


def test_sync_all_isolates_failures(three):
    sync, path = three
    calls = []

    def fake(url):
        calls.append(url)
        if "yandex" in url:
            raise ICalError("Не удалось скачать календарь: 500")
        return AVITO_FEED if "avito" in url else feed(("s1", "20261215", "20261217"))
    sync.update_platform("sutochno", enabled=False)
    reports = sync.sync_all(today=TODAY, fetch=fake)
    assert set(reports) == {"avito", "yandex"} and reports["avito"]["ok"] and not reports["yandex"]["ok"]
    assert len(calls) == 2                                                       # выключенная площадка не опрашивается
    assert sorted({b["source"] for b in rows(path)}) == ["ical_avito"]
    assert set(sync.sync_all(only_enabled=False, today=TODAY, fetch=fake)) == {"avito", "yandex", "sutochno"}


def test_manual_booking_replaces_blocks_of_its_own_platform_only(three):
    sync, path = three
    run_sync(sync, feed(("a", "20261101", "20261104")), source="avito")
    run_sync(sync, feed(("y", "20261101", "20261104")), source="yandex")      # из Яндекса: даты уже заняты блокировкой Авито -> пропущено
    assert [b["source"] for b in rows(path)] == ["ical_avito"]
    assert sync.manual_booking_replaces_blocks("2026-11-01", "2026-11-04", "yandex") == 0
    assert sync.manual_booking_replaces_blocks("2026-11-01", "2026-11-04", "phone") == 0
    assert sync.manual_booking_replaces_blocks("2026-11-01", "2026-11-04", "avito") == 1
    assert [b["status"] for b in rows(path)] == ["cancelled"]


def test_manual_booking_handler_calls_replacement_with_source(three, monkeypatch):
    sync, path = three
    from fastapi import HTTPException
    import routers.bookings as rb
    from core.models import ManualBookingCreate
    calls = []
    monkeypatch.setattr(rb, "manual_booking_replaces_blocks", lambda a, b, s: calls.append((a, b, s)) or 0)
    monkeypatch.setattr(rb, "is_dates_available", lambda *a, **k: False)         # дальше нам важна только подготовка
    for source in ("yandex", "avito", "phone", "unknown-source"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(rb.create_manual_booking(ManualBookingCreate(source=source, check_in="2026-11-01", check_out="2026-11-04", guests_count=2, total_price=5000), True))
        assert e.value.status_code == 409
    assert calls == [("2026-11-01", "2026-11-04", s) for s in ("yandex", "avito", "phone", "other")]
    sync.add_platform("Моя площадка", "myplat")
    asyncio.run(_try_manual(rb, "myplat"))
    assert calls[-1][2] == "myplat"                                              # источник из «Интеграций» принимается


async def _try_manual(rb, source):
    from fastapi import HTTPException
    from core.models import ManualBookingCreate
    try:
        await rb.create_manual_booking(ManualBookingCreate(source=source, check_in="2026-11-01", check_out="2026-11-04", guests_count=2, total_price=5000), True)
    except HTTPException:
        pass


# --- ссылки, токены, API ---------------------------------------------------------

def test_public_endpoint_serves_only_by_platform_token(three):
    sync, _ = three
    from fastapi import HTTPException
    from routers.ical import public_calendar
    token = sync.get_platform("avito")["export_token"]
    assert sync.export_url(sync.get_platform("avito")).endswith(f"/ical/{token}.ics")
    response = asyncio.run(public_calendar(f"{token}.ics"))
    assert response.status_code == 200 and response.media_type.startswith("text/calendar")
    assert response.body.startswith(b"BEGIN:VCALENDAR")
    for wrong in ("wrong.ics", token, f"{token}x.ics", ".ics", "", "avito.ics", "yandex.ics"):
        with pytest.raises(HTTPException) as e:
            asyncio.run(public_calendar(wrong))
        assert e.value.status_code == 404
    old = token
    new = sync.regenerate_token("avito")["export_token"]
    assert new != old
    with pytest.raises(HTTPException):
        asyncio.run(public_calendar(f"{old}.ics"))                               # старая ссылка больше не работает
    assert asyncio.run(public_calendar(f"{new}.ics")).status_code == 200
    # у каждой площадки свой токен: ссылка Яндекса не открывает календарь Авито и наоборот
    tokens = {p["source"]: p["export_token"] for p in sync.list_platforms()}
    assert len(set(tokens.values())) == 3


def test_public_endpoint_closed_when_no_platforms(env):
    from fastapi import HTTPException
    from routers.ical import public_calendar
    with pytest.raises(HTTPException) as e:
        asyncio.run(public_calendar("anything.ics"))
    assert e.value.status_code == 404


def test_admin_endpoints_require_admin_and_work(env):
    import inspect
    from fastapi import HTTPException
    from core.auth import require_admin
    from core.models import CalendarPlatformCreate, CalendarPlatformUpdate
    from routers import ical as r
    for func in (r.get_calendars, r.add_calendar, r.update_calendar, r.delete_calendar,
                 r.sync_all_calendars, r.sync_calendar, r.regenerate_calendar_token):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"
    state = asyncio.run(r.get_calendars(True))
    assert state["platforms"] == [] and state["max_platforms"] == 30 and any(p["source"] == "avito" for p in state["presets"])
    state = asyncio.run(r.add_calendar(CalendarPlatformCreate(name="Авито", source="avito"), True))
    view = state["platforms"][0]
    assert view["name"] == "Авито" and view["export_url"].endswith(".ics") and "export_token" not in view
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.add_calendar(CalendarPlatformCreate(name="Авито", source="avito"), True))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.update_calendar("avito", CalendarPlatformUpdate(url="ftp://x.example.com/c.ics"), True))
    assert e.value.status_code == 400
    state = asyncio.run(r.update_calendar("avito", CalendarPlatformUpdate(url=" https://avito.example.com/c.ics ", enabled=False), True))
    assert state["platforms"][0]["url"] == "https://avito.example.com/c.ics" and state["platforms"][0]["enabled"] is False
    with pytest.raises(HTTPException) as e:
        asyncio.run(r.sync_calendar("nope", True))
    assert e.value.status_code == 404
    state = asyncio.run(r.delete_calendar("avito", True))
    assert state["platforms"] == [] and state["removed_blocks"] == 0


# ---------------------------------------------------------------------------
# Настоящая загрузка по HTTP (локальный сервер, проверка адреса отключена только в тесте)
# ---------------------------------------------------------------------------

def _serve(body: bytes, status=200):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "text/calendar")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_fetch_ical_over_http(monkeypatch):
    monkeypatch.setattr(ical, "check_calendar_url", lambda url, resolve=True: url)
    server = _serve(AVITO_FEED.encode("utf-8"))
    try:
        text = ical.fetch_ical(f"http://127.0.0.1:{server.server_port}/cal.ics")
    finally:
        server.shutdown()
    assert [e["uid"] for e in parse_ical(text)] == ["avito-1", "avito-2"]


def test_fetch_ical_rejects_huge_and_failed_responses(monkeypatch):
    monkeypatch.setattr(ical, "check_calendar_url", lambda url, resolve=True: url)
    monkeypatch.setattr(ical, "MAX_ICAL_BYTES", 1000)
    big = _serve(b"x" * 5000)
    try:
        with pytest.raises(ICalError, match="большой"):
            ical.fetch_ical(f"http://127.0.0.1:{big.server_port}/cal.ics")
    finally:
        big.shutdown()
    failing = _serve(b"error", status=500)
    try:
        with pytest.raises(ICalError, match="Не удалось скачать"):
            ical.fetch_ical(f"http://127.0.0.1:{failing.server_port}/cal.ics")
    finally:
        failing.shutdown()


def test_fetch_ical_blocks_local_addresses_without_patching():
    with pytest.raises(ICalError):
        ical.fetch_ical("http://127.0.0.1:9/cal.ics")
