import sqlite3
import os

DB_PATH = "data/bookings.db"


# =====================================================
# GET CONNECTION
# =====================================================

def get_connection():

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


# =====================================================
# INIT DB
# =====================================================

def init_db():

    os.makedirs("data", exist_ok=True)

    with get_connection() as conn:

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

    print("✅ SQLITE DATABASE INITIALIZED")


# =====================================================
# CHECK DATE OVERLAP
# =====================================================

def is_dates_available(check_in, check_out):

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        SELECT id
        FROM bookings

        WHERE status IN ('confirmed', 'blocked')

        AND (

            (? < check_out)
            AND
            (? > check_in)

        )

        LIMIT 1

        """, (

            check_in,
            check_out

        ))

        conflict = cursor.fetchone()

        return conflict is None


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

    available = is_dates_available(
        check_in,
        check_out
    )

    if not available:

        raise Exception(
            "DATES_NOT_AVAILABLE"
        )

    with get_connection() as conn:

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

        booking_id = cursor.lastrowid

        print(
            f"✅ BOOKING CREATED #{booking_id}"
        )

        return booking_id


# =====================================================
# GET ALL BOOKINGS
# =====================================================

def get_all_bookings():

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        SELECT

            id,
            user_id,
            username,
            check_in,
            check_out,
            guests,
            status,
            created_at

        FROM bookings

        ORDER BY id DESC

        """)

        rows = cursor.fetchall()

        return [dict(row) for row in rows]


# =====================================================
# GET BOOKED RANGES
# =====================================================

def get_booked_ranges():

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        SELECT

            check_in,
            check_out

        FROM bookings

        WHERE status IN (

            'confirmed',
            'blocked'

        )

        """)

        rows = cursor.fetchall()

    return [

        {
            "check_in": row["check_in"],
            "check_out": row["check_out"]
        }

        for row in rows
    ]


# =====================================================
# GET BOOKING BY ID
# =====================================================

def get_booking_by_id(booking_id):

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        SELECT *
        FROM bookings

        WHERE id = ?

        LIMIT 1

        """, (booking_id,))

        row = cursor.fetchone()

        if row:

            return dict(row)

        return None


# =====================================================
# CANCEL BOOKING
# =====================================================

def cancel_booking(booking_id):

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        UPDATE bookings

        SET status = 'cancelled'

        WHERE id = ?

        """, (booking_id,))

        conn.commit()

        print(
            f"🛑 BOOKING CANCELLED #{booking_id}"
        )


# =====================================================
# BLOCK DATES
# =====================================================

def block_dates(check_in, check_out):

    available = is_dates_available(
        check_in,
        check_out
    )

    if not available:

        raise Exception(
            "DATES_ALREADY_BOOKED"
        )

    with get_connection() as conn:

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

        print(
            f"🔒 DATES BLOCKED {check_in} → {check_out}"
        )


# =====================================================
# DELETE BOOKING
# =====================================================

def delete_booking(booking_id):

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute("""

        DELETE FROM bookings

        WHERE id = ?

        """, (booking_id,))

        conn.commit()

        print(
            f"❌ BOOKING DELETED #{booking_id}"
        )


# =====================================================
# DEBUG
# =====================================================

print("✅ BOOKING SERVICE LOADED")
print(f"📁 DATABASE PATH: {DB_PATH}")