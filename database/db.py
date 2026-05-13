import sqlite3
from contextlib import contextmanager

# ⚠️ ВАЖНО: Railway volume путь
DB_PATH = "/data/bookings.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    finally:
        conn.close()