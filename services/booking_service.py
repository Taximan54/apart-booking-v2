from database.db import get_db


# =====================================================
# CREATE BOOKING
# =====================================================

def create_booking(
    user_id: int,
    username: str,
    date: str,
    time: str,
    guests: int
):
    with get_db() as conn:

        cursor = conn.execute("""
            INSERT INTO bookings (
                user_id,
                username,
                date,
                time,
                guests
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            date,
            time,
            guests
        ))

        return cursor.lastrowid


# =====================================================
# GET ALL BOOKINGS
# =====================================================

def get_all_bookings():

    with get_db() as conn:

        rows = conn.execute("""
            SELECT *
            FROM bookings
            ORDER BY created_at DESC
        """).fetchall()

        return [dict(row) for row in rows]


# =====================================================
# UPDATE STATUS
# =====================================================

def update_booking_status(
    booking_id: int,
    status: str
):

    with get_db() as conn:

        conn.execute("""
            UPDATE bookings
            SET status = ?
            WHERE id = ?
        """, (
            status,
            booking_id
        ))