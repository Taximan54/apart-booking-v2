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


def get_default_deposit():
    """Депозит по умолчанию — из раздела «Тарифы» в админке (PRICE_FILE), с фолбэком на DEFAULT_PRICES."""
    if os.path.exists(PRICE_FILE):
        try:
            with open(PRICE_FILE, "r") as f:
                saved = json.load(f)
            return int(saved.get("deposit", DEFAULT_PRICES["deposit"]))
        except Exception:
            pass
    return DEFAULT_PRICES["deposit"]

def get_site_settings_dict():
    """Внутренний helper — читает настройки сайта с мержем дефолтов (без require_admin)."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    return DEFAULT_SETTINGS

# =====================================================
# API — PLACES (Куда сходить)
# =====================================================

def load_places():
    if os.path.exists(PLACES_FILE):
        with open(PLACES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    return []

# =====================================================
# API — DISCOUNTS (Скидки и акции)
# =====================================================

def load_discounts():
    if os.path.exists(DISCOUNTS_FILE):
        with open(DISCOUNTS_FILE, "r", encoding="utf-8") as f:
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
