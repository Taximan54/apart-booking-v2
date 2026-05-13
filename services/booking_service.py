import sqlite3
from datetime import datetime

DB_PATH = "bookings.db"


# =====================================================
# INIT DB
# =====================================================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER
        )
        """)


# =====================================================
# CHECK OVERLAP (AIRBNB LOGIC)
# =====================================================
def is_overlapping(check_in, check_out):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM bookings
            WHERE NOT (
                date(check_out) <= date(?)
                OR date(check_in) >= date(?)
            )
        """, (check_in, check_out))

        return cursor.fetchone() is not None


# =====================================================
# CREATE BOOKING
# =====================================================
def create_booking(user_id, username, check_in, check_out, guests):

    if is_overlapping(check_in, check_out):
        raise Exception("Даты уже заняты")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO bookings (user_id, username, check_in, check_out, guests)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, check_in, check_out, guests))

        conn.commit()

        return cursor.lastrowid


# =====================================================
# GET BOOKED DATES (FOR CALENDAR)
# =====================================================
def get_booked_dates():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT check_in, check_out FROM bookings")
        rows = cursor.fetchall()

    blocked = []

    for start, end in rows:
        d1 = datetime.strptime(start, "%Y-%m-%d")
        d2 = datetime.strptime(end, "%Y-%m-%d")

        current = d1
        while current <= d2:
            blocked.append(current.strftime("%Y-%m-%d"))
            current = current.replace(day=current.day + 1)

    return list(set(blocked))


# =====================================================
# GET ALL BOOKINGS (FOR ADMIN PANEL)
# =====================================================
def get_all_bookings():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, username, check_in, check_out, guests
            FROM bookings
            ORDER BY id DESC
        """)

        rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "username": r[2],
            "check_in": r[3],
            "check_out": r[4],
            "guests": r[5],
        }
        for r in rows
    ]


# =====================================================
# ADMIN COMPATIBILITY (FIX RAILWAY CRASH)
# =====================================================
def update_booking_status(booking_id, status="active"):
    """
    Заглушка, чтобы admin.py не ломал импорт.
    Можно расширить позже.
    """
    return {
        "booking_id": booking_id,
        "status": status
    }