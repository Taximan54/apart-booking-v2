import os
import sqlite3

DB_PATH = "/data/bookings.db"


# =====================================================
# INIT DB
# =====================================================
def init_db():
    os.makedirs("/data", exist_ok=True)

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
# CREATE BOOKING (С ЗАЩИТОЙ ОТ ПЕРЕСЕЧЕНИЙ)
# =====================================================
def create_booking(user_id, username, check_in, check_out, guests):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT 1 FROM bookings
        WHERE NOT (
            date(check_out) <= date(?)
            OR date(check_in) >= date(?)
        )
        """, (check_in, check_out))

        if cursor.fetchone():
            raise Exception("Даты заняты")

        cursor.execute("""
        INSERT INTO bookings (user_id, username, check_in, check_out, guests)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, check_in, check_out, guests))

        conn.commit()
        return cursor.lastrowid


# =====================================================
# WEBAPP: занятые даты
# =====================================================
def get_booked_ranges():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT check_in, check_out FROM bookings")

        return [
            {"check_in": r[0], "check_out": r[1]}
            for r in cursor.fetchall()
        ]


# =====================================================
# ADMIN (НЕ ЛОМАЕТСЯ ДАЖЕ ЕСЛИ СТАРЫЙ КОД ЕСТЬ)
# =====================================================
def get_all_bookings():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookings ORDER BY id DESC")
        return cursor.fetchall()


def update_booking_status(*args, **kwargs):
    return True