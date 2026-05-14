import sqlite3
import os

DB_PATH = "data/bookings.db"


# =====================================================
# INIT DB
# =====================================================

def init_db():

    os.makedirs("data", exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER,
            status TEXT DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()


# =====================================================
# CREATE BOOKING
# =====================================================

def create_booking(
    user_id,
    username,
    check_in,
    check_out,
    guests
):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO bookings (
            user_id,
            username,
            check_in,
            check_out,
            guests,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            username,
            check_in,
            check_out,
            guests,
            "confirmed"
        ))

        conn.commit()

        return cursor.lastrowid


# =====================================================
# GET ALL BOOKINGS
# =====================================================

def get_all_bookings():

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            id,
            username,
            check_in,
            check_out,
            guests,
            status
        FROM bookings
        ORDER BY id DESC
        """)

        return cursor.fetchall()


# =====================================================
# GET BOOKED RANGES
# =====================================================

def get_booked_ranges():

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        SELECT check_in, check_out
        FROM bookings
        WHERE status IN ('confirmed', 'blocked')
        """)

        rows = cursor.fetchall()

    return [
        {
            "check_in": row[0],
            "check_out": row[1]
        }
        for row in rows
    ]


# =====================================================
# CANCEL BOOKING
# =====================================================

def cancel_booking(booking_id):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        UPDATE bookings
        SET status = 'cancelled'
        WHERE id = ?
        """, (booking_id,))

        conn.commit()


# =====================================================
# BLOCK DATES
# =====================================================

def block_dates(check_in, check_out):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO bookings (
            user_id,
            username,
            check_in,
            check_out,
            guests,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            0,
            "ADMIN_BLOCK",
            check_in,
            check_out,
            0,
            "blocked"
        ))

        conn.commit()