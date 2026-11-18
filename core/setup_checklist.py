"""Чек-лист «Что осталось заполнить»: только читает данные и ничего не меняет."""
import json
import os

import config
from core import mailer
from core.backup import get_backup_password
from core.constants import (
    CONTACTS_FILE,
    DEFAULT_LANDLORD,
    DEFAULT_SETTINGS,
    PAYMENT_FILE,
    PAYMENT_QR_PATH,
    PRICE_FILE,
)
from core.contract_settings import load_contract_settings
from core.data_store import get_site_settings_dict
from core.landlord import get_landlord
from core.logger import get_logger
from core.noindex import noindex_enabled
from core.properties import property_file

logger = get_logger(__name__)


def _read_json(path: str) -> dict:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Чек-лист: не удалось прочитать %s: %s", path, e)
    return {}


def _filled(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _photos_count(property_id: int) -> int:
    from routers.photos import get_photos_list   # позже, чтобы не создавать круговой импорт
    return len(get_photos_list(property_id))


def _item(key, title, done, panel=None, tab=None, server=False, hint=""):
    return {"key": key, "title": title, "done": bool(done), "panel": panel, "tab": tab, "server": server, "hint": hint}


def build_checklist(property_id: int) -> dict:
    """Список пунктов для выбранного объекта; пункты «на сервере» одинаковы для всех объектов."""
    landlord = get_landlord()
    contacts = _read_json(CONTACTS_FILE)
    payment = _read_json(PAYMENT_FILE)
    site = get_site_settings_dict(property_id)
    contract = load_contract_settings(property_id)
    try:
        photos = _photos_count(property_id)
    except Exception as e:
        logger.warning("Чек-лист: не удалось посчитать фото: %s", e)
        photos = 0

    items = [
        _item("landlord", "Данные арендодателя: название, адрес сайта, адрес",
              all(landlord.get(k) and landlord[k] != DEFAULT_LANDLORD[k] for k in DEFAULT_LANDLORD), panel="settings"),
        _item("contacts", "Контакты: почта и хотя бы один способ связи",
              _filled(contacts.get("email")) and any(_filled(contacts.get(k)) for k in ("phone", "telegram", "whatsapp", "max")),
              panel="contacts"),
        _item("payment", "Оплата (СБП): ссылка, телефон или QR-код",
              _filled(payment.get("sbp_link")) or _filled(payment.get("sbp_phone")) or os.path.exists(PAYMENT_QR_PATH),
              panel="contacts"),
        _item("site_name", "Название сайта (этой квартиры)",
              _filled(site.get("site_name")) and site["site_name"] != DEFAULT_SETTINGS["site_name"], panel="sitesettings", tab="brand"),
        _item("address", "Адрес квартиры на странице («Расположение»)", _filled(site.get("location_address")),
              panel="sitesettings", tab="location"),
        _item("photos", "Фото квартиры в галерее", photos > 0, panel="photos"),
        _item("prices", "Цены (сохраните раздел «Цены» хотя бы раз)",
              os.path.exists(property_file(PRICE_FILE, property_id)), panel="prices"),
        _item("contract", "Данные объекта для договора: арендодатель и адрес",
              _filled(contract.get("landlord_name")) and _filled(contract.get("address")), panel="contract"),
        _item("mail", "Почта для писем гостям (MAIL_FROM и MAIL_PASSWORD)",
              bool(mailer.MAIL_FROM) and bool(mailer.MAIL_PASSWORD), panel="monitoring", server=True,
              hint="Задаётся в файле .env на сервере. Проверить: Мониторинг → «Отправить тестовое письмо»."),
        _item("base_url", "Адрес сайта для ссылок в письмах (BASE_URL)", bool(config.BASE_URL), server=True,
              hint="Задаётся в файле .env на сервере, например BASE_URL=https://example.ru"),
        _item("backup_password", "Пароль резервных копий (BACKUP_PASSWORD)", bool(get_backup_password()), server=True,
              hint="Задаётся в файле .env на сервере. Без него копии не шифруются и на почту не уходят."),
        _item("indexing", "Сайт открыт для поисковиков (убрать NOINDEX из .env)", not noindex_enabled(), server=True,
              hint="Пока в .env есть NOINDEX=1, поисковики сайт не показывают. Уберите строку, когда будете готовы к запуску."),
    ]
    done = sum(1 for i in items if i["done"])
    return {"property_id": property_id, "items": items, "done": done, "total": len(items), "complete": done == len(items)}
