import json
import os

BOOKINGS_FILE = "data/bookings.json"

# =====================================================
# СОЗДАНИЕ ФАЙЛА
# =====================================================

def ensure_file():

    if not os.path.exists("data"):
        os.makedirs("data")

    if not os.path.exists(BOOKINGS_FILE):

        with open(
            BOOKINGS_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump([], f)

# =====================================================
# ЗАГРУЗКА
# =====================================================

def load_bookings():

    ensure_file()

    try:

        with open(
            BOOKINGS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:

        return []

# =====================================================
# СОХРАНЕНИЕ
# =====================================================

def save_bookings(data):

    ensure_file()

    with open(
        BOOKINGS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )