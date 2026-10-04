"""Подключение к базе данных бронирований."""
import sqlite3

from core.constants import DB_FILE


# =====================================================
# DATABASE
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 0,
            username TEXT,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER DEFAULT 2,
            status TEXT DEFAULT 'waiting_payment',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    # Добавляем колонки если их нет
    for col, col_type in {
        "guest_name":     "TEXT DEFAULT ''",
        "guest_phone":    "TEXT DEFAULT ''",
        "guest_email":    "TEXT DEFAULT ''",
        "guests_count":   "INTEGER DEFAULT 2",
        "notes":          "TEXT DEFAULT ''",
        "passport":       "TEXT DEFAULT ''",
        "payment_method": "TEXT DEFAULT 'tbank'",
        "total_price":    "INTEGER DEFAULT 0",
        "nights":         "INTEGER DEFAULT 1",
        "source":         "TEXT DEFAULT 'website'",
        "confirmed_at":   "TEXT DEFAULT ''",
        "promo_code":     "TEXT DEFAULT ''",
        "discount_percent": "INTEGER DEFAULT 0",
        "fully_paid_at":  "TEXT DEFAULT ''",
        "checklist_sent": "INTEGER DEFAULT 0",
        "review_sent":    "INTEGER DEFAULT 0",
        "sign_token": "TEXT DEFAULT ''",
        "signed_at":  "TEXT DEFAULT ''",
        "sign_ip":    "TEXT DEFAULT ''",
        "deposit":    "INTEGER DEFAULT 0",
        "deposit_returned":    "INTEGER DEFAULT 0",
        "deposit_returned_at": "TEXT DEFAULT ''",
    }.items():
        try:
            conn.execute("ALTER TABLE bookings ADD COLUMN " + col + " " + col_type)
            conn.commit()
        except Exception:
            pass
    return conn
