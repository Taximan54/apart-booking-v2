from database.db import get_db


def create_booking(user_id: int, username: str, date: str, time: str, guests: int):
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO bookings (user_id, username, date, time, guests)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, date, time, guests))

        return cursor.lastrowid


def get_all_bookings():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM bookings
            ORDER BY created_at DESC
        """).fetchall()

        return [dict(row) for row in rows]