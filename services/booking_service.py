```python
import sqlite3
from pathlib import Path

# =====================================================
# DATABASE PATH
# =====================================================

DB_PATH = "data/bookings.db"

# =====================================================
# CREATE DATA FOLDER
# =====================================================

Path("data").mkdir(exist_ok=True)

# =====================================================
# INIT DB
# =====================================================

def init_db():

    Path(DB_PATH).touch(exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,
            username TEXT,

            check_in TEXT,
            check_out TEXT,

            guests INTEGER DEFAULT 1,

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
    guests=1
):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        # ПРОВЕРКА ПЕРЕСЕЧЕНИЯ ДАТ
        cursor.execute("""
        SELECT *
        FROM bookings
        WHERE status IN ('confirmed', 'blocked')
        AND (
            check_in <= ?
            AND check_out >= ?
        )
        """, (check_out, check_in))

        conflict = cursor.fetchone()

        if conflict:
            raise Exception("Даты уже заняты")

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
        SELECT
            check_in,
            check_out
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
# UPDATE BOOKING STATUS
# =====================================================

def update_booking_status(booking_id, status):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        UPDATE bookings
        SET status = ?
        WHERE id = ?
        """, (status, booking_id))

        conn.commit()


# =====================================================
# DELETE BOOKING
# =====================================================

def delete_booking(booking_id):

    with sqlite3.connect(DB_PATH) as conn:

        cursor = conn.cursor()

        cursor.execute("""
        DELETE FROM bookings
        WHERE id = ?
        """, (booking_id,))

        conn.commit()
```
