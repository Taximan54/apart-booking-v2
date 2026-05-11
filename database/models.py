from database.db import get_connection

def create_tables():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        booking_id TEXT,

        checkin TEXT,

        checkout TEXT,

        nights INTEGER,

        total INTEGER,

        status TEXT
    )
    """)

    conn.commit()

    conn.close()