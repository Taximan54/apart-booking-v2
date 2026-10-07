"""
Работа с таблицей броней (bookings): все SQL-запросы к ней собраны здесь.

Обработчики адресов API, рассылки и кнопки Telegram не пишут SQL сами, а
вызывают эти функции. Каждая функция сама открывает соединение, выполняет запрос
(для записи — сохраняет изменения) и закрывает соединение.
"""
from typing import Optional

from core.db import find_booking_row, get_db

# Поля гостя, которые можно дозаполнить при подписании (имена колонок — только из этого списка)
GUEST_FIELDS = ("guest_name", "guest_phone", "guest_email", "passport")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _fetch_one(sql: str, params: tuple) -> Optional[dict]:
    conn = get_db()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _write(sql: str, params: tuple) -> int:
    """Выполняет запись и возвращает число изменённых строк."""
    conn = get_db()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------

def list_bookings() -> list:
    """Все брони, новые заезды сверху."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM bookings ORDER BY check_in DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_by_ref(ref: str) -> Optional[dict]:
    """Бронь по номеру (username), например GP-ABC123."""
    return _fetch_one("SELECT * FROM bookings WHERE username=? LIMIT 1", (ref,))


def get_by_ref_or_id(value: str) -> Optional[dict]:
    """Бронь по номеру или по id (значение приходит строкой из адреса)."""
    return _fetch_one("SELECT * FROM bookings WHERE username=? OR CAST(id AS TEXT)=? LIMIT 1", (value, value))


def get_by_id_or_ref(value: str) -> Optional[dict]:
    """Бронь по id или по номеру."""
    return _fetch_one("SELECT * FROM bookings WHERE id=? OR username=?", (value, value))


def get_by_ref_alt(ref: str) -> Optional[dict]:
    """Бронь по номеру, старому номеру «ГП-…» или id."""
    conn = get_db()
    try:
        row = find_booking_row(conn, ref)
        return dict(row) if row else None
    finally:
        conn.close()


def get_by_sign_token(token: str) -> Optional[dict]:
    """Бронь по токену из ссылки на подписание."""
    return _fetch_one("SELECT * FROM bookings WHERE sign_token=?", (token,))


def get_sign_state(ref: str) -> Optional[dict]:
    """Токен подписания и дата подписи по номеру брони (поля sign_token, signed_at)."""
    return _fetch_one("SELECT sign_token, signed_at FROM bookings WHERE username = ?", (ref,))


def exists_by_ref(ref: str) -> bool:
    return _fetch_one("SELECT id FROM bookings WHERE username = ?", (ref,)) is not None


def find_blocked_ids(property_id, start: str, end_exclusive: str) -> list:
    """id блокировок дат, пересекающихся с диапазоном."""
    conn = get_db()
    try:
        rows = conn.execute("""
        SELECT id FROM bookings
        WHERE property_id = ? AND status = 'blocked'
        AND check_in < ? AND check_out > ?
    """, (property_id, end_exclusive, start)).fetchall()
        return [row["id"] for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Создание
# ---------------------------------------------------------------------------

def insert_website_booking(property_id, ref, check_in, check_out, guests_count, guest_name, guest_phone,
                           guest_email, notes, passport, payment_method, total_price, nights,
                           promo_code, discount_percent) -> None:
    """Бронь, созданная гостем на сайте (статус waiting_payment)."""
    _write("""
            INSERT INTO bookings (
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, guest_phone, guest_email, guests_count,
                notes, passport, payment_method, total_price, nights, source,
                promo_code, discount_percent
            ) VALUES (?, 0, ?, ?, ?, ?, 'waiting_payment', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'website', ?, ?)
        """, (
        property_id,
        ref, check_in, check_out, guests_count,
        guest_name, guest_phone, guest_email, guests_count,
        notes, passport, payment_method, total_price, nights,
        promo_code, discount_percent,
    ))


def insert_manual_booking(property_id, ref, check_in, check_out, guests_count, guest_name, guest_phone,
                          guest_email, notes, passport, total_price, nights, source, deposit,
                          sign_token) -> None:
    """Бронь, созданная администратором вручную (статус confirmed)."""
    _write("""
            INSERT INTO bookings (
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, guest_phone, guest_email, guests_count,
                notes, passport, payment_method, total_price, nights, source,
                promo_code, discount_percent, deposit, sign_token
            ) VALUES (?, 0, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?, ?, ?, 'external', ?, ?, ?, '', 0, ?, ?)
        """, (
        property_id,
        ref, check_in, check_out, guests_count,
        guest_name, guest_phone, guest_email, guests_count,
        notes, passport, total_price, nights, source,
        deposit, sign_token,
    ))


def insert_block(property_id, ref, check_in, check_out, reason, nights) -> None:
    """Блокировка дат администратором."""
    _write("""
            INSERT INTO bookings (
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, notes, total_price, nights, source
            ) VALUES (?, 0, ?, ?, ?, 0, 'blocked', 'Заблокировано администратором', ?, 0, ?, 'admin_block')
        """, (property_id, ref, check_in, check_out, reason, nights))


# ---------------------------------------------------------------------------
# Изменение
# ---------------------------------------------------------------------------

def set_sign_token_by_ref(ref: str, token: str) -> None:
    _write("UPDATE bookings SET sign_token=? WHERE username=?", (token, ref))


def set_sign_token_by_id(booking_id, token: str) -> None:
    _write("UPDATE bookings SET sign_token=? WHERE id=?", (token, booking_id))


def set_status_by_id(booking_id, status: str) -> None:
    _write("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))


def set_status_by_ref(ref: str, status: str) -> None:
    _write("UPDATE bookings SET status=? WHERE username=?", (status, ref))


def cancel_blocks(ids: list) -> None:
    """Отменяет блокировки дат (одной операцией)."""
    if not ids:
        return
    conn = get_db()
    try:
        conn.executemany("UPDATE bookings SET status='cancelled' WHERE id=?", [(i,) for i in ids])
        conn.commit()
    finally:
        conn.close()


def confirm_with_token(booking_id, confirmed_at: str, sign_token: str) -> None:
    """Подтверждение оплаты: статус confirmed, время и новый токен подписания."""
    _write("UPDATE bookings SET status='confirmed', confirmed_at=?, sign_token=? WHERE id=?",
           (confirmed_at, sign_token, booking_id))


def mark_fully_paid(value, paid_at: str) -> None:
    """Полная оплата (бронь ищется по id или номеру)."""
    _write("UPDATE bookings SET status='fully_paid', fully_paid_at=? WHERE id=? OR username=?",
           (paid_at, value, value))


def mark_checklist_sent(booking_id, ref) -> None:
    _write("UPDATE bookings SET checklist_sent=1 WHERE id=? OR username=?", (booking_id, ref))


def mark_review_sent(booking_id, ref) -> None:
    _write("UPDATE bookings SET review_sent=1 WHERE id=? OR username=?", (booking_id, ref))


def mark_deposit_returned(ref: str, returned_at: str) -> None:
    _write("UPDATE bookings SET deposit_returned=1, deposit_returned_at=? WHERE username=?",
           (returned_at, ref))


def sign_booking(booking_id, signed_at: str, sign_ip: str, guest_fields: Optional[dict] = None) -> None:
    """
    Подписание договора: записывает дату и IP подписи и (если переданы) дозаполненные
    данные гостя — всё одной операцией: либо всё сохранилось, либо ничего.
    guest_fields: словарь из GUEST_FIELDS (guest_name, guest_phone, guest_email, passport).
    """
    conn = get_db()
    try:
        for column, value in (guest_fields or {}).items():
            if column not in GUEST_FIELDS:
                raise ValueError(f"Недопустимое поле брони: {column}")
            conn.execute(f"UPDATE bookings SET {column}=? WHERE id=?", (value, booking_id))
        conn.execute("UPDATE bookings SET signed_at=?, sign_ip=? WHERE id=?", (signed_at, sign_ip, booking_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Удаление
# ---------------------------------------------------------------------------

def delete_by_ref_alt(ref: str) -> Optional[str]:
    """
    Удаляет бронь, найденную по номеру (в том числе по старому «ГП-…») или id.
    Возвращает номер удалённой брони (username или id) или None, если брони нет.
    """
    conn = get_db()
    try:
        row = find_booking_row(conn, ref)
        if not row:
            return None
        deleted_ref = row["username"] or str(row["id"])
        conn.execute("DELETE FROM bookings WHERE id=?", (row["id"],))
        conn.commit()
        return deleted_ref
    finally:
        conn.close()
