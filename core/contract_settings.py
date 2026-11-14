"""Данные объекта для договора аренды: арендодатель, вид объекта, адрес, перечень имущества.
Хранятся у каждого объекта отдельно; пустое поле = «взять по умолчанию» (так договор остаётся прежним, пока ничего не заполнено)."""
import json
import os

from core.constants import CONTRACT_SETTINGS_FILE
from core.logger import get_logger
from core.properties import property_file

logger = get_logger(__name__)

FIELDS = ("landlord_name", "object_kind", "address", "inventory", "basis")
LIMITS = {"landlord_name": 200, "object_kind": 100, "address": 300, "inventory": 8000, "basis": 500}


def load_contract_settings(property_id: int) -> dict:
    result = {key: "" for key in FIELDS}
    path = property_file(CONTRACT_SETTINGS_FILE, property_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in FIELDS:
                value = saved.get(key)
                if isinstance(value, str):
                    result[key] = value.strip()
        except Exception as e:
            logger.warning("Не удалось прочитать данные объекта для договора: %s", e)
    return result


def save_contract_settings(property_id: int, data: dict) -> dict:
    clean = {key: str(data.get(key) or "").strip()[:LIMITS[key]] for key in FIELDS}
    path = property_file(CONTRACT_SETTINGS_FILE, property_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False)
    return clean
