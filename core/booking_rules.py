"""Правила бронирования объекта: минимальный срок в ночах. У каждого объекта свой (по умолчанию 2)."""
import json
import os

from core.constants import DATA_DIR
from core.logger import get_logger
from core.properties import property_file

logger = get_logger(__name__)

# Основной объект хранит правила здесь, остальные: /data/properties/<номер>/booking_rules.json
BOOKING_RULES_FILE = os.path.join(DATA_DIR, "booking_rules.json")
DEFAULT_MIN_NIGHTS = 2
MIN_LIMIT, MAX_LIMIT = 1, 30


def clean_min_nights(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_NIGHTS
    return max(MIN_LIMIT, min(MAX_LIMIT, number))


def get_min_nights(property_id: int = 1) -> int:
    """Минимальный срок бронирования объекта. Нет файла или он повреждён: 2 ночи, как было раньше."""
    path = property_file(BOOKING_RULES_FILE, property_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return clean_min_nights(json.load(f).get("min_nights"))
        except Exception as e:
            logger.warning("Не удалось прочитать правила бронирования объекта %s: %s", property_id, e)
    return DEFAULT_MIN_NIGHTS


def set_min_nights(property_id: int, value) -> int:
    number = clean_min_nights(value)
    path = property_file(BOOKING_RULES_FILE, property_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"min_nights": number}, f, ensure_ascii=False)
    os.replace(tmp, path)
    return number


def ru_nights(n: int) -> str:
    """1 ночь, 2 ночи, 5 ночей."""
    m, d = n % 100, n % 10
    word = "ночей" if 11 <= m <= 14 else "ночь" if d == 1 else "ночи" if 2 <= d <= 4 else "ночей"
    return f"{n} {word}"
