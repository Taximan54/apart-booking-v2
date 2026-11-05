"""Автоотмена броней с сайта, если оплата не подтверждена за заданное время."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core import bookings_repo as repo
from core import payment_timeout as pt


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "b.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER, user_id INTEGER, "
        "username TEXT, check_in TEXT, check_out TEXT, guests INTEGER, status TEXT, guest_name TEXT, "
        "guest_phone TEXT, guest_email TEXT, guests_count INTEGER, notes TEXT, passport TEXT, "
        "payment_method TEXT, total_price INTEGER, nights INTEGER, source TEXT, promo_code TEXT, "
        "discount_percent INTEGER)"
    )
    conn.commit()
    conn.close()

    def fake_db():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(repo, "get_db", fake_db)
    monkeypatch.setattr(pt, "PAYMENT_CONFIRM_FILE", str(tmp_path / "payment_confirm.json"))
    return path


def _add(ref="GP-000001"):
    repo.insert_website_booking(1, ref, "2027-01-10", "2027-01-12", 2, "Гость", "+79000000000", "g@example.com",
                                "", "", "sbp", 7000, 2, "", 0)


def _age(db_path, ref, hours):
    old = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE bookings SET waiting_since = ? WHERE username = ?", (old, ref))
    conn.commit()
    conn.close()


def _status(db_path, ref):
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM bookings WHERE username = ?", (ref,)).fetchone()
    conn.close()
    return row[0]


def test_hours_default_set_and_clamp(db):
    assert pt.get_confirm_hours() == 2
    assert pt.set_confirm_hours(5) == 5
    assert pt.get_confirm_hours() == 5
    assert pt.set_confirm_hours(999) == pt.MAX_CONFIRM_HOURS
    assert pt.set_confirm_hours(-3) == 0
    assert pt.set_confirm_hours("abc") == pt.DEFAULT_CONFIRM_HOURS


def test_new_website_booking_has_waiting_since(db):
    _add()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert [b["username"] for b in repo.list_expired_unpaid(future)] == ["GP-000001"]
    assert repo.list_expired_unpaid(past) == []


def test_expired_booking_is_cancelled_and_admin_notified(db, monkeypatch):
    notified = []
    monkeypatch.setattr(pt, "_notify_admin", lambda b, h: notified.append((b["username"], h)))
    pt.set_confirm_hours(2)
    _add("GP-000001")   # старая
    _add("GP-000002")   # свежая
    _age(db, "GP-000001", 3)
    cancelled = pt.run_expire()
    assert [b["username"] for b in cancelled] == ["GP-000001"]
    assert _status(db, "GP-000001") == "cancelled"
    assert _status(db, "GP-000002") == "waiting_payment"
    assert notified == [("GP-000001", 2)]


def test_payment_pending_is_cancelled_too_but_confirmed_is_not(db, monkeypatch):
    monkeypatch.setattr(pt, "_notify_admin", lambda b, h: None)
    pt.set_confirm_hours(1)
    _add("GP-000001")
    _add("GP-000002")
    _age(db, "GP-000001", 2)
    _age(db, "GP-000002", 2)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bookings SET status='payment_pending' WHERE username='GP-000001'")
    conn.execute("UPDATE bookings SET status='confirmed' WHERE username='GP-000002'")
    conn.commit()
    conn.close()
    pt.run_expire()
    assert _status(db, "GP-000001") == "cancelled"
    assert _status(db, "GP-000002") == "confirmed"


def test_zero_hours_disables_and_manual_bookings_are_ignored(db, monkeypatch):
    monkeypatch.setattr(pt, "_notify_admin", lambda b, h: None)
    _add("GP-000001")
    _age(db, "GP-000001", 100)
    pt.set_confirm_hours(0)
    assert pt.run_expire() == []
    assert _status(db, "GP-000001") == "waiting_payment"
    pt.set_confirm_hours(1)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bookings SET source='avito' WHERE username='GP-000001'")
    conn.commit()
    conn.close()
    assert pt.run_expire() == []
    assert _status(db, "GP-000001") == "waiting_payment"


def test_old_bookings_without_timestamp_are_not_touched(db, monkeypatch):
    monkeypatch.setattr(pt, "_notify_admin", lambda b, h: None)
    _add("GP-000001")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bookings SET waiting_since = NULL")
    conn.commit()
    conn.close()
    pt.set_confirm_hours(1)
    assert pt.run_expire() == []
    assert _status(db, "GP-000001") == "waiting_payment"


def test_cancel_unpaid_does_not_override_confirmed(db):
    _add()
    conn = sqlite3.connect(db)
    conn.execute("UPDATE bookings SET status='confirmed'")
    conn.commit()
    conn.close()
    assert repo.cancel_unpaid_by_id(1) is False


def test_public_endpoint_returns_hours_for_site(db):
    import asyncio
    from routers import content
    pt.set_confirm_hours(4)
    assert asyncio.run(content.get_public_payment_confirm()) == {"hours": 4}
    pt.set_confirm_hours(0)
    assert asyncio.run(content.get_public_payment_confirm()) == {"hours": 0}
