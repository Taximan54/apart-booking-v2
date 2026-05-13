import sqlite3
from datetime import datetime

DB_PATH = "bookings.db"


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