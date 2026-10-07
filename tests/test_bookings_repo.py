"""Слой работы с бронями (core/bookings_repo.py) на настоящей базе SQLite во временном файле."""
import asyncio
import sqlite3
import types

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Пустая база с таблицей броней как на сервере (колонку property_id там создаёт services)."""
    import core.db as database
    path = str(tmp_path / "bookings.db")
    monkeypatch.setattr(database, "DB_FILE", path)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER DEFAULT 1, "
        "user_id INTEGER DEFAULT 0, username TEXT, check_in TEXT, check_out TEXT, guests INTEGER DEFAULT 2, "
        "status TEXT DEFAULT 'waiting_payment', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()
    return path


def row(db_path, ref):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM bookings WHERE username=?", (ref,)).fetchone()
    conn.close()
    return dict(r) if r else None


def make_website(repo, ref="GP-AAA111", check_in="2027-03-10", check_out="2027-03-12", name="Иван"):
    repo.insert_website_booking(1, ref, check_in, check_out, 2, name, "+79990000000", "a@b.c",
                                "заметка", "1234 567890", "tbank", 9000, 2, "PROMO", 10)


def test_insert_website_booking_and_reads(db):
    from core import bookings_repo as repo
    make_website(repo)
    b = repo.get_by_ref("GP-AAA111")
    assert b["status"] == "waiting_payment" and b["source"] == "website"
    assert (b["guest_name"], b["total_price"], b["nights"], b["promo_code"], b["discount_percent"]) == ("Иван", 9000, 2, "PROMO", 10)
    assert repo.get_by_ref_or_id("GP-AAA111")["id"] == b["id"]
    assert repo.get_by_ref_or_id(str(b["id"]))["username"] == "GP-AAA111"
    assert repo.get_by_id_or_ref(str(b["id"]))["username"] == "GP-AAA111"
    assert repo.get_by_ref("GP-NOPE") is None and repo.get_by_ref_or_id("NOPE") is None
    assert repo.exists_by_ref("GP-AAA111") and not repo.exists_by_ref("GP-NOPE")
    assert [x["username"] for x in repo.list_bookings()] == ["GP-AAA111"]


def test_list_is_sorted_by_check_in_desc(db):
    from core import bookings_repo as repo
    make_website(repo, "GP-OLD", "2027-01-01", "2027-01-03")
    make_website(repo, "GP-NEW", "2027-06-01", "2027-06-03")
    assert [x["username"] for x in repo.list_bookings()] == ["GP-NEW", "GP-OLD"]


def test_manual_booking_and_sign_token(db):
    from core import bookings_repo as repo
    repo.insert_manual_booking(1, "GP-MAN111", "2027-04-01", "2027-04-03", 2, "", "", "", "", "", 5000, 2, "avito", 3000, "tok-1")
    b = repo.get_by_sign_token("tok-1")
    assert b["username"] == "GP-MAN111" and b["status"] == "confirmed" and b["source"] == "avito" and b["deposit"] == 3000
    assert repo.get_by_sign_token("nope") is None
    state = repo.get_sign_state("GP-MAN111")
    assert state["sign_token"] == "tok-1" and not state["signed_at"]
    repo.set_sign_token_by_ref("GP-MAN111", "tok-2")
    assert repo.get_by_ref("GP-MAN111")["sign_token"] == "tok-2"
    repo.set_sign_token_by_id(b["id"], "tok-3")
    assert repo.get_by_sign_token("tok-3")["id"] == b["id"]


def test_status_changes(db):
    from core import bookings_repo as repo
    make_website(repo)
    b = repo.get_by_ref("GP-AAA111")
    repo.set_status_by_ref("GP-AAA111", "payment_pending")
    assert row(db, "GP-AAA111")["status"] == "payment_pending"
    repo.confirm_with_token(b["id"], "2027-01-01T10:00:00", "tok-x")
    r = row(db, "GP-AAA111")
    assert (r["status"], r["confirmed_at"], r["sign_token"]) == ("confirmed", "2027-01-01T10:00:00", "tok-x")
    repo.mark_fully_paid("GP-AAA111", "2027-01-02 12:00")
    r = row(db, "GP-AAA111")
    assert (r["status"], r["fully_paid_at"]) == ("fully_paid", "2027-01-02 12:00")
    repo.set_status_by_id(b["id"], "cancelled")
    assert row(db, "GP-AAA111")["status"] == "cancelled"


def test_flags_and_deposit(db):
    from core import bookings_repo as repo
    make_website(repo)
    b = repo.get_by_ref("GP-AAA111")
    repo.mark_checklist_sent(b["id"], "GP-AAA111")
    repo.mark_review_sent(b["id"], "GP-AAA111")
    repo.mark_deposit_returned("GP-AAA111", "2027-03-13 10:00:00")
    r = row(db, "GP-AAA111")
    assert (r["checklist_sent"], r["review_sent"], r["deposit_returned"], r["deposit_returned_at"]) == (1, 1, 1, "2027-03-13 10:00:00")


def test_blocks_create_find_cancel(db):
    from core import bookings_repo as repo
    repo.insert_block(1, "BLOCK-AAA111", "2027-05-01", "2027-05-03", "ремонт", 2)
    repo.insert_block(1, "BLOCK-BBB222", "2027-06-01", "2027-06-02", "", 1)
    b = row(db, "BLOCK-AAA111")
    assert (b["status"], b["source"], b["guest_name"], b["notes"]) == ("blocked", "admin_block", "Заблокировано администратором", "ремонт")
    ids = repo.find_blocked_ids(1, "2027-05-01", "2027-05-02")
    assert ids == [b["id"]]
    assert repo.find_blocked_ids(1, "2027-07-01", "2027-07-02") == []
    assert repo.find_blocked_ids(2, "2027-05-01", "2027-05-02") == []     # другой объект
    repo.cancel_blocks(ids)
    assert row(db, "BLOCK-AAA111")["status"] == "cancelled" and row(db, "BLOCK-BBB222")["status"] == "blocked"
    repo.cancel_blocks([])                                                   # пустой список безопасен


def test_sign_booking_with_guest_fields_is_atomic(db):
    from core import bookings_repo as repo
    repo.insert_manual_booking(1, "GP-MAN111", "2027-04-01", "2027-04-03", 2, "", "", "", "", "", 5000, 2, "avito", 0, "tok-1")
    b = repo.get_by_ref("GP-MAN111")
    repo.sign_booking(b["id"], "2027-04-01 10:00:00", "1.2.3.4",
                      {"guest_name": "Пётр", "guest_phone": "+79991112233", "guest_email": "p@p.ru", "passport": "1234 567890"})
    r = row(db, "GP-MAN111")
    assert (r["guest_name"], r["guest_phone"], r["guest_email"], r["passport"]) == ("Пётр", "+79991112233", "p@p.ru", "1234 567890")
    assert (r["signed_at"], r["sign_ip"]) == ("2027-04-01 10:00:00", "1.2.3.4")
    # недопустимое поле: ни подпись, ни данные не записываются
    make_website(repo, "GP-BBB222")
    b2 = repo.get_by_ref("GP-BBB222")
    with pytest.raises(ValueError):
        repo.sign_booking(b2["id"], "2027-04-02 10:00:00", "5.6.7.8", {"guest_name": "Х", "status": "confirmed"})
    r2 = row(db, "GP-BBB222")
    assert r2["guest_name"] == "Иван" and not r2["signed_at"] and r2["status"] == "waiting_payment"


def test_ref_alt_and_delete(db):
    from core import bookings_repo as repo
    make_website(repo, "\u0413\u041f-OLD111")          # старая бронь с русским префиксом
    assert repo.get_by_ref_alt("GP-OLD111")["username"] == "\u0413\u041f-OLD111"
    assert repo.get_by_ref_alt("GP-NOPE") is None
    assert repo.delete_by_ref_alt("GP-NOPE") is None
    assert repo.delete_by_ref_alt("GP-OLD111") == "\u0413\u041f-OLD111"
    assert repo.list_bookings() == []


def test_telegram_buttons_use_repo(db, monkeypatch):
    """Кнопки «подтвердить/отклонить» в Telegram меняют статус брони."""
    import core.telegram_callbacks as tc
    from core import bookings_repo as repo
    make_website(repo, "GP-TG1111")
    make_website(repo, "GP-TG2222", "2027-08-01", "2027-08-03")
    monkeypatch.setattr(tc, "ADMIN_IDS", [42])
    emails = []
    monkeypatch.setattr(tc, "email_booking_confirmed", lambda booking, code: emails.append(booking["username"]))

    def fake_callback(data):
        async def edit_text(text):
            return None

        async def answer(text=None):
            return None
        return types.SimpleNamespace(
            data=data, from_user=types.SimpleNamespace(id=42),
            message=types.SimpleNamespace(text="Оплата", edit_text=edit_text), answer=answer,
        )

    asyncio.run(tc.web_payment_confirm(fake_callback("web_confirm_GP-TG1111")))
    asyncio.run(tc.web_payment_reject(fake_callback("web_reject_GP-TG2222")))
    assert row(db, "GP-TG1111")["status"] == "confirmed"
    assert row(db, "GP-TG2222")["status"] == "cancelled"
    assert emails == ["GP-TG1111"]
    # чужой пользователь ничего не меняет
    stranger = fake_callback("web_reject_GP-TG1111")
    stranger.from_user.id = 7
    asyncio.run(tc.web_payment_reject(stranger))
    assert row(db, "GP-TG1111")["status"] == "confirmed"
