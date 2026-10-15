"""Общие функции чтения данных из JSON-файлов (настройки, места, акции, депозит и т.д.)."""
import json
import os

from core.constants import (
    PRICE_FILE,
    DEFAULT_PRICES,
    SETTINGS_FILE,
    DEFAULT_SETTINGS,
    PLACES_FILE,
    DISCOUNTS_FILE,
    PROPERTIES_FILE,
    OWNER_NOTIFY_FILE,
)
from core.logger import get_logger
from core.properties import property_file
from services.booking_service import DEFAULT_PROPERTY_ID

logger = get_logger(__name__)


def get_default_deposit(property_id: int = DEFAULT_PROPERTY_ID):
    """Депозит по умолчанию — из раздела «Тарифы» в админке (PRICE_FILE), с фолбэком на DEFAULT_PRICES."""
    price_file = property_file(PRICE_FILE, property_id)
    if os.path.exists(price_file):
        try:
            with open(price_file, "r") as f:
                saved = json.load(f)
            return int(saved.get("deposit", DEFAULT_PRICES["deposit"]))
        except Exception as e:
            logger.warning("Не удалось прочитать депозит из файла цен: %s", e)
    return DEFAULT_PRICES["deposit"]

def get_site_settings_dict(property_id: int = DEFAULT_PROPERTY_ID):
    """Внутренний helper — читает настройки сайта с мержем дефолтов (без require_admin)."""
    settings_file = property_file(SETTINGS_FILE, property_id)
    if os.path.exists(settings_file):
        with open(settings_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    return DEFAULT_SETTINGS

# =====================================================
# API — PLACES (Куда сходить)
# =====================================================

def load_places(property_id: int = DEFAULT_PROPERTY_ID):
    places_file = property_file(PLACES_FILE, property_id)
    if os.path.exists(places_file):
        with open(places_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []

# =====================================================
# API — DISCOUNTS (Скидки и акции)
# =====================================================

def load_discounts(property_id: int = DEFAULT_PROPERTY_ID):
    discounts_file = property_file(DISCOUNTS_FILE, property_id)
    if os.path.exists(discounts_file):
        with open(discounts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []

def load_properties():
    """
    Реестр квартир. Сейчас всегда одна запись (id=1) — структурная готовность
    на будущее (white-label с несколькими объектами), без лишнего UI пока не нужно.
    """
    if os.path.exists(PROPERTIES_FILE):
        with open(PROPERTIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    default = [{
        "id": 1,
        "name": "Городская Пауза",
        "address": "Новосибирск, ул. Дачная, д. 5, кв. 286",
        "active": True,
    }]
    with open(PROPERTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(default, f, ensure_ascii=False)
    return default

def get_last_owner_notify_date():
    """Дата последнего отправленного владельцу уведомления о выездах (чтобы не дублировать в течение дня)."""
    if os.path.exists(OWNER_NOTIFY_FILE):
        with open(OWNER_NOTIFY_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_date", "")
    return ""

def set_last_owner_notify_date(date_str):
    with open(OWNER_NOTIFY_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_date": date_str}, f)
