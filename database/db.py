import sqlite3

DB_NAME = "database/database.db"


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
            checkin TEXT,
            checkout TEXT,
            nights INTEGER,
            total INTEGER,
            status TEXT
        )
    """)

    conn.commit()
    conn.close()