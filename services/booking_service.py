import sqlite3

DB_PATH = "/data/bookings.db"


# =====================================================
# INIT DB
# =====================================================

def init_booking_table():

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

            status TEXT DEFAULT 'confirmed'
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

        # =========================================
        # CHECK OVERLAP
        # =========================================

        cursor.execute("""
        SELECT * FROM bookings
        WHERE status = 'confirmed'
        AND (
            check_in <= ?
            AND check_out >= ?
        )
        """, (check_out, check_in))

        exists = cursor.fetchone()

        if exists:
            raise Exception("Даты уже заняты")

        # =========================================
        # CREATE
        # =========================================

        cursor.execute("""
        INSERT INTO bookings (

            user_id,
            username,
            check_in,
            check_out,
            guests

        ) VALUES (?, ?, ?, ?, ?)
        """, (

            user_id,
            username,
            check_in,
            check_out,
            guests

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

        rows = cursor.fetchall()

    return rows


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

        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (

            0,
            "BLOCKED",
            check_in,
            check_out,
            0,
            "blocked"

        ))

        conn.commit()


# =====================================================
# BOOKED RANGES
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
            "check_in": r[0],
            "check_out": r[1]
        }
        for r in rows
    ]