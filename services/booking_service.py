import os
import sqlite3
from datetime import datetime

# =====================================================
# DATABASE PATH (RAILWAY VOLUME)
# =====================================================
DB_PATH = "/data/bookings.db"


# =====================================================
# INIT DB (FULL RESET FIX)
# =====================================================
def init_db():
    os.makedirs("/data", exist_ok=True)

    # 🔥 УДАЛЯЕМ СТАРУЮ КРИВУЮ БАЗУ
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # 🔥 СОЗДАЁМ НОВУЮ ЧИСТУЮ БАЗУ
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER
        )
        """)
        conn.commit()


# =====================================================
# CHECK OVERLAP (AIRBNB LOGIC)
# =====================================================
def is_overlapping(check_in, check_out):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM bookings
            WHERE NOT (
                date(check_out) <= date(?)
                OR date(check_in) >= date(?)
            )
            LIMIT 1
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
        try:
            d1 = datetime.strptime(start, "%Y-%m-%d")
            d2 = datetime.strptime(end, "%Y-%m-%d")

            current = d1
            while current <= d2:
                blocked.append(current.strftime("%Y-%m-%d"))
                current = current.replace(day=current.day + 1)
        except:
            continue

    return list(set(blocked))


# =====================================================
# GET ALL BOOKINGS (ADMIN)
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
# ADMIN COMPATIBILITY (NO CRASH)
# =====================================================
def update_booking_status(booking_id, status="active"):
    return {
        "booking_id": booking_id,
        "status": status
    }