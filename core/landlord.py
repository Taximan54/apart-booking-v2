"""Данные арендодателя: название бренда, домен сайта, адрес и почта (из настроек, с запасными значениями)."""
import json
import os
import re

from core.constants import CONTACTS_FILE, DEFAULT_LANDLORD, LANDLORD_EMAIL, LANDLORD_FILE
from core.logger import get_logger

logger = get_logger(__name__)


def clean_domain(value: str) -> str:
    """Приводит ввод к виду «example.ru»: без https://, www. и лишних слэшей."""
    d = (value or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0].strip()


def get_landlord() -> dict:
    """Настройки арендодателя. Пустые поля заменяются значениями по умолчанию."""
    saved = {}
    if os.path.exists(LANDLORD_FILE):
        try:
            with open(LANDLORD_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception as e:
            logger.warning("Не удалось прочитать настройки арендодателя: %s", e)
    result = dict(DEFAULT_LANDLORD)
    for key in DEFAULT_LANDLORD:
        value = (saved.get(key) or "").strip() if isinstance(saved.get(key), str) else ""
        if value:
            result[key] = value
    result["domain"] = clean_domain(result["domain"]) or DEFAULT_LANDLORD["domain"]
    return result


def landlord_brand() -> str:
    return get_landlord()["brand_name"]


def landlord_domain() -> str:
    return get_landlord()["domain"]


def landlord_address() -> str:
    return get_landlord()["address"]


def site_url() -> str:
    """Адрес сайта с https:// (для ссылок в письмах)."""
    return "https://" + get_landlord()["domain"]


def get_landlord_email() -> str:
    """Почта арендодателя: из раздела «Контакты», иначе запасная из констант."""
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                email = (json.load(f).get("email") or "").strip()
            if email:
                return email
        except Exception as e:
            logger.warning("Не удалось прочитать почту из контактов: %s", e)
    return LANDLORD_EMAIL
