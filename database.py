import sqlite3

DB_NAME = "bookings.db"


def get_connection():

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        CREATE TABLE IF NOT EXISTS bookings (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            check_in TEXT NOT NULL,

            check_out TEXT NOT NULL,

            guest_name TEXT,

            guests INTEGER DEFAULT 1,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

    """)

    conn.commit()

    conn.close()