"""
Объекты (квартиры): реестр, выбор объекта в запросе и пути к данным объекта.

Объект № 1 — исходная квартира, её данные лежат там же, где всегда (/data/prices.json и т.д.),
поэтому ничего переносить не нужно. Данные остальных объектов лежат отдельно:
/data/properties/<номер объекта>/<то же имя файла>.
"""
import json
import os
import re
import shutil
from typing import Optional

from fastapi import Header, HTTPException, Query

from core import bookings_repo as repo
from core.auth import verify_token
from core.constants import (
    CHECKIN_FILE,
    CHECKOUT_FILE,
    DATA_DIR,
    DESC_FILE,
    DISCOUNTS_FILE,
    HOUSE_RULES_FILE,
    PLACES_FILE,
    PRICE_FILE,
    PROPERTIES_FILE,
    SETTINGS_FILE,
)
from core.logger import get_logger
from services.booking_service import DEFAULT_PROPERTY_ID

logger = get_logger(__name__)

PROPERTIES_DIR = os.path.join(DATA_DIR, "properties")
MAX_PROPERTIES = 50
RESERVED_SLUGS = {"admin", "api", "static", "data", "ical", "sign", "complete", "discounts", "o", "main"}


class PropertyError(Exception):
    """Ошибка в данных объекта (понятный текст для админа)."""


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

def _load() -> list:
    items = []
    if os.path.exists(PROPERTIES_FILE):
        try:
            with open(PROPERTIES_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception as e:
            logger.warning("Не удалось прочитать реестр объектов: %s", e)
    if not isinstance(items, list) or not any(p.get("id") == DEFAULT_PROPERTY_ID for p in items):
        # Объект № 1 есть всегда
        items = [p for p in items if isinstance(p, dict)] if isinstance(items, list) else []
        items.insert(0, {"id": DEFAULT_PROPERTY_ID, "name": "Городская Пауза",
                         "address": "Новосибирск, ул. Дачная, д. 5, кв. 286", "active": True})
    normalized = []
    for p in items:
        normalized.append({
            "id": int(p["id"]),
            "name": p.get("name") or f"Объект {p['id']}",
            "address": p.get("address") or "",
            "active": p.get("active", True) is not False,
            "slug": p.get("slug") or "",
        })
    return normalized


def _save(items: list) -> None:
    os.makedirs(os.path.dirname(PROPERTIES_FILE), exist_ok=True)
    with open(PROPERTIES_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)


def list_properties() -> list:
    return _load()


def get_property(property_id: int) -> Optional[dict]:
    return next((p for p in _load() if p["id"] == property_id), None)


def get_property_by_slug(slug: str) -> Optional[dict]:
    slug = (slug or "").strip().lower()
    return next((p for p in _load() if p["slug"] and p["slug"] == slug), None)


def _clean_slug(slug: str, items: list, own_id: Optional[int] = None) -> str:
    slug = (slug or "").strip().lower()
    if not slug:
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,39}", slug):
        raise PropertyError("Адрес страницы: 2–40 символов, латиница, цифры и «-»")
    if slug in RESERVED_SLUGS:
        raise PropertyError("Этот адрес зарезервирован, выберите другой")
    if any(p["slug"] == slug and p["id"] != own_id for p in items):
        raise PropertyError("Такой адрес страницы уже занят")
    return slug


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        raise PropertyError("Укажите название объекта")
    if len(name) > 80:
        raise PropertyError("Название слишком длинное (макс. 80 символов)")
    return name


def create_property(name: str, address: str = "", slug: str = "") -> dict:
    items = _load()
    if len(items) >= MAX_PROPERTIES:
        raise PropertyError(f"Можно создать не больше {MAX_PROPERTIES} объектов")
    name = _clean_name(name)
    new_id = max(p["id"] for p in items) + 1
    slug = _clean_slug(slug, items) or f"obj-{new_id}"
    if any(p["slug"] == slug for p in items):
        slug = f"obj-{new_id}"
    prop = {"id": new_id, "name": name, "address": (address or "").strip()[:200], "active": True, "slug": slug}
    items.append(prop)
    _save(items)
    os.makedirs(os.path.join(PROPERTIES_DIR, str(new_id)), exist_ok=True)
    return prop


def update_property(property_id: int, name: Optional[str] = None, address: Optional[str] = None,
                    active: Optional[bool] = None, slug: Optional[str] = None) -> dict:
    items = _load()
    prop = next((p for p in items if p["id"] == property_id), None)
    if not prop:
        raise PropertyError("Объект не найден")
    if name is not None:
        prop["name"] = _clean_name(name)
    if address is not None:
        prop["address"] = address.strip()[:200]
    if slug is not None and property_id != DEFAULT_PROPERTY_ID:
        prop["slug"] = _clean_slug(slug, items, own_id=property_id) or prop["slug"]
    if active is not None:
        if property_id == DEFAULT_PROPERTY_ID and not active:
            raise PropertyError("Основной объект нельзя отключить")
        prop["active"] = bool(active)
    _save(items)
    return prop


def delete_property(property_id: int) -> None:
    """Удаляет объект вместе с его настройками. Нельзя удалить основной объект и объект с бронями."""
    if property_id == DEFAULT_PROPERTY_ID:
        raise PropertyError("Основной объект удалить нельзя")
    items = _load()
    if not any(p["id"] == property_id for p in items):
        raise PropertyError("Объект не найден")
    if repo.count_bookings(property_id) > 0:
        raise PropertyError("У объекта есть брони или блокировки дат. Отключите объект вместо удаления")
    _save([p for p in items if p["id"] != property_id])
    shutil.rmtree(os.path.join(PROPERTIES_DIR, str(property_id)), ignore_errors=True)


# ---------------------------------------------------------------------------
# Копирование настроек из другого объекта
# ---------------------------------------------------------------------------
# Копируются: цены, описание, правила проживания, памятка, чек-лист, настройки сайта, места, акции.
# НЕ копируются: фото (и ссылки на них), отзывы, код замка, брони и блокировки, адрес в договоре.

COPYABLE_FILES = (PRICE_FILE, DESC_FILE, HOUSE_RULES_FILE, CHECKIN_FILE, CHECKOUT_FILE,
                  SETTINGS_FILE, PLACES_FILE, DISCOUNTS_FILE)
# Поля с фото и картой квартиры: в копии очищаются, чтобы у нового объекта не показывались чужие фото
_OWN_FIELDS = {"photo", "photo_mobile", "hero_photo", "hero_photo_mobile", "map_photo", "map_url"}


def _without_own_fields(obj):
    if isinstance(obj, dict):
        return {k: ("" if k in _OWN_FIELDS and isinstance(v, str) else _without_own_fields(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_without_own_fields(v) for v in obj]
    return obj


def copy_property_settings(source_id: int, target_id: int) -> list:
    """
    Копирует настройки объекта source_id в объект target_id. Исходный объект не меняется.
    Ошибка с одним файлом не мешает остальным. Возвращает имена скопированных файлов.
    """
    copied = []
    if source_id == target_id:
        return copied
    for legacy in COPYABLE_FILES:
        try:
            src = property_file(legacy, source_id)
            if not os.path.exists(src):
                continue
            dst = property_file(legacy, target_id)
            if legacy.endswith(".json"):
                with open(src, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(_without_own_fields(data), f, ensure_ascii=False)
            else:
                shutil.copyfile(src, dst)
            copied.append(os.path.basename(legacy))
        except Exception as e:
            logger.warning("Не удалось скопировать %s из объекта %s в объект %s: %s",
                           os.path.basename(legacy), source_id, target_id, e)
    return copied


# ---------------------------------------------------------------------------
# Данные объекта
# ---------------------------------------------------------------------------

def property_file(legacy_path: str, property_id: int = DEFAULT_PROPERTY_ID) -> str:
    """
    Путь к файлу данных объекта. Для основного объекта это обычный путь (как раньше),
    для остальных — такой же файл в папке /data/properties/<номер>/.
    """
    if property_id == DEFAULT_PROPERTY_ID:
        return legacy_path
    folder = os.path.join(PROPERTIES_DIR, str(int(property_id)))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, os.path.basename(legacy_path))


# ---------------------------------------------------------------------------
# Выбор объекта в запросе
# ---------------------------------------------------------------------------

def admin_property_id(x_property_id: Optional[str] = Header(None, alias="X-Property-Id")) -> int:
    """Объект, с которым работает админка (заголовок X-Property-Id; без него — основной)."""
    if not x_property_id:
        return DEFAULT_PROPERTY_ID
    try:
        property_id = int(x_property_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный номер объекта")
    if not get_property(property_id):
        raise HTTPException(status_code=404, detail="Объект не найден")
    return property_id


def public_property_id(property: Optional[str] = Query(None)) -> int:
    """Объект, который открыл гость (адрес страницы объекта в ?property=...; без него — основной)."""
    if not property:
        return DEFAULT_PROPERTY_ID
    prop = get_property_by_slug(property)
    if not prop or not prop["active"]:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return prop["id"]


def request_property_id(
    x_property_id: Optional[str] = Header(None, alias="X-Property-Id"),
    property: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> int:
    """
    Объект для адресов, которые открыты и сайту, и админке (цены, фото, описание и т.п.):
    админка передаёт номер объекта заголовком X-Property-Id, сайт — адрес страницы объекта в ?property=...
    Отключённый объект виден только администратору.
    """
    if x_property_id:
        property_id = admin_property_id(x_property_id)
        prop = get_property(property_id)
        if prop and not prop["active"]:
            token = authorization[len("Bearer "):] if authorization and authorization.startswith("Bearer ") else ""
            if not token or not verify_token(token):
                raise HTTPException(status_code=404, detail="Объект не найден")
        return property_id
    return public_property_id(property)
