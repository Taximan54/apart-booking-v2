"""
Каталог апартаментов: страница «Все апартаменты» (/apartments), на которой гость выбирает квартиру.

Каталог всегда синхронизирован с объектами: список берётся из реестра объектов, поэтому новый объект
появляется в каталоге сам, а удалённый или отключённый исчезает. Отдельно хранятся только настройки каталога
(тексты страницы, оформление и по каждому объекту: показывать ли, название, подпись, свой адрес сайта, порядок)
в /data/catalog.json. Они общие для всех объектов.
"""
import json
import os
import re
from urllib.parse import quote

from core.constants import DATA_DIR, DEFAULT_PRICES, DESC_FILE, PRICE_FILE, SETTINGS_FILE
from core.data_store import get_site_settings_dict
from core.landlord import landlord_brand
from core.logger import get_logger
from core.properties import list_properties, property_file
from services.booking_service import DEFAULT_PROPERTY_ID

logger = get_logger(__name__)

CATALOG_FILE = os.path.join(DATA_DIR, "catalog.json")

DEFAULT_TITLE = "Наши апартаменты"
DEFAULT_SUBTITLE = "Выберите квартиру для своего отдыха"

# Темы оформления совпадают с темами сайта (index.html и page-theme.js)
BACKGROUND_THEMES = ("black", "white", "pistachio", "cream", "midnight", "sand", "mocha", "emerald_night", "terracotta", "indigo")
COLOR_THEMES = ("gold", "emerald", "sapphire", "burgundy", "amethyst", "dusty_rose", "teal", "copper", "graphite", "onyx")

MAX_PHOTOS = 12
MAX_AMENITIES = 6


class CatalogError(Exception):
    """Ошибка в настройках каталога (понятный текст для админа)."""


# ---------------------------------------------------------------------------
# Настройки каталога
# ---------------------------------------------------------------------------

def _clean_item(item, truncate: bool = True) -> dict:
    """Приводит запись об объекте к единому виду. truncate=False — без обрезки (для проверки введённого админом)."""
    def text(key, limit):
        value = str(item.get(key) or "").strip()
        return value[:limit] if truncate else value
    return {
        "id": int(item["id"]),
        "visible": item.get("visible", True) is not False,
        "title": text("title", 80),
        "caption": text("caption", 120),
        "site_url": text("site_url", 300),
    }


def load_catalog_settings() -> dict:
    data = {}
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Не удалось прочитать настройки каталога: %s", e)
    if not isinstance(data, dict):
        data = {}
    items = []
    for item in data.get("items") or []:
        try:
            items.append(_clean_item(item))
        except Exception:
            continue
    background = data.get("background_theme")
    color = data.get("color_theme")
    return {
        "brand": str(data.get("brand") or "").strip()[:80],
        "title": str(data.get("title") or "").strip()[:100],
        "subtitle": str(data.get("subtitle") or "").strip()[:300],
        "background_theme": background if background in BACKGROUND_THEMES else "",
        "color_theme": color if color in COLOR_THEMES else "",
        "items": items,
    }


def _check_site_url(url: str) -> None:
    if not url:
        return
    if len(url) > 300 or re.search(r"\s", url) or not (url.startswith("http://") or url.startswith("https://") or url.startswith("/")):
        raise CatalogError("Свой адрес сайта должен начинаться с http://, https:// или «/», без пробелов")


def save_catalog_settings(brand, title, subtitle, background_theme, color_theme, items) -> dict:
    brand, title, subtitle = (brand or "").strip(), (title or "").strip(), (subtitle or "").strip()
    if len(brand) > 80:
        raise CatalogError("Название сети слишком длинное (макс. 80 символов)")
    if len(title) > 100:
        raise CatalogError("Заголовок слишком длинный (макс. 100 символов)")
    if len(subtitle) > 300:
        raise CatalogError("Подзаголовок слишком длинный (макс. 300 символов)")
    if background_theme and background_theme not in BACKGROUND_THEMES:
        raise CatalogError("Неизвестный фон")
    if color_theme and color_theme not in COLOR_THEMES:
        raise CatalogError("Неизвестный цвет")
    clean, seen = [], set()
    for item in items or []:
        row = _clean_item(item if isinstance(item, dict) else (item.model_dump() if hasattr(item, "model_dump") else item.dict()), truncate=False)
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        if len(row["title"]) > 80:
            raise CatalogError("Название в каталоге слишком длинное (макс. 80 символов)")
        if len(row["caption"]) > 120:
            raise CatalogError("Подпись слишком длинная (макс. 120 символов)")
        _check_site_url(row["site_url"])
        clean.append(row)
    data = {"brand": brand, "title": title, "subtitle": subtitle, "background_theme": background_theme or "",
            "color_theme": color_theme or "", "items": clean}
    os.makedirs(os.path.dirname(CATALOG_FILE), exist_ok=True)
    tmp = CATALOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, CATALOG_FILE)
    return load_catalog_settings()


# ---------------------------------------------------------------------------
# Объекты в каталоге (синхронизация с реестром объектов)
# ---------------------------------------------------------------------------

def _merged_items() -> list:
    """Все объекты реестра с их настройками каталога: сначала в сохранённом порядке, новые объекты в конце."""
    props = list_properties()
    by_id = {p["id"]: p for p in props}
    config, order = {}, []
    for item in load_catalog_settings()["items"]:
        if item["id"] in by_id and item["id"] not in config:
            config[item["id"]] = item
            order.append(item["id"])
    for prop in props:
        if prop["id"] not in config:
            config[prop["id"]] = {"id": prop["id"], "visible": True, "title": "", "caption": "", "site_url": ""}
            order.append(prop["id"])
    return [(by_id[i], config[i]) for i in order]


def object_url(prop: dict, cfg: dict) -> str:
    custom = (cfg.get("site_url") or "").strip()
    if custom:
        return custom
    if prop["id"] == DEFAULT_PROPERTY_ID or not prop.get("slug"):
        return "/"
    return "/o/" + quote(prop["slug"])


def _own_site_name(prop: dict) -> str:
    """Название сайта объекта из его настроек (если настроек у объекта ещё нет, берётся название объекта)."""
    if os.path.exists(property_file(SETTINGS_FILE, prop["id"])):
        name = str(get_site_settings_dict(prop["id"]).get("site_name") or "").strip()
        if name:
            return name
    return prop["name"]


def _prices(property_id: int) -> dict:
    data = dict(DEFAULT_PRICES)
    path = property_file(PRICE_FILE, property_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception as e:
            logger.warning("Каталог: не удалось прочитать цены объекта %s: %s", property_id, e)
    return data


def _price_from(prices: dict) -> int:
    values = []
    for key in ("weekday", "weekend"):
        try:
            value = int(prices.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            values.append(value)
    return min(values) if values else 0


def _excerpt(property_id: int, limit: int = 220) -> str:
    path = property_file(DESC_FILE, property_id)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = re.sub(r"\s+", " ", f.read()).strip()
    except Exception:
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-– ") + "…"
    return text


def _photos(property_id: int, settings: dict) -> list:
    from routers.photos import get_photos_list   # импорт здесь, чтобы не создавать циклов при запуске
    photos = [{"url": p["url"], "label": p.get("label") or ""} for p in get_photos_list(property_id)][:MAX_PHOTOS]
    if not photos and settings.get("hero_photo"):
        photos = [{"url": f"/data/photos/{settings['hero_photo']}", "label": ""}]
    return photos


def _amenities(settings: dict) -> list:
    result = []
    for item in settings.get("amenities") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            result.append({"icon": str(item.get("icon") or "").strip()[:8], "name": name[:60]})
        if len(result) >= MAX_AMENITIES:
            break
    return result


# ---------------------------------------------------------------------------
# Данные для гостей и для админки
# ---------------------------------------------------------------------------

def build_public_catalog() -> dict:
    settings = load_catalog_settings()
    main_settings = get_site_settings_dict(DEFAULT_PROPERTY_ID)
    items = []
    for prop, cfg in _merged_items():
        if not prop["active"] or not cfg["visible"]:
            continue
        try:
            site = get_site_settings_dict(prop["id"])
            prices = _prices(prop["id"])
            photos = _photos(prop["id"], site)
            items.append({
                "id": prop["id"],
                "name": cfg["title"] or _own_site_name(prop),
                "caption": cfg["caption"],
                "url": object_url(prop, cfg),
                "description": _excerpt(prop["id"]),
                "price_from": _price_from(prices),
                "amenities": _amenities(site),
                "photos": photos,
            })
        except Exception as e:
            logger.warning("Каталог: не удалось собрать объект %s: %s", prop.get("id"), e)
    return {
        "brand": settings["brand"] or landlord_brand(),
        "title": settings["title"] or DEFAULT_TITLE,
        "subtitle": settings["subtitle"] or DEFAULT_SUBTITLE,
        "background_theme": settings["background_theme"] or main_settings.get("background_theme") or "black",
        "color_theme": settings["color_theme"] or main_settings.get("color_theme") or "gold",
        "count": len(items),
        "items": items,
    }


def admin_catalog_state() -> dict:
    settings = load_catalog_settings()
    rows = []
    for prop, cfg in _merged_items():
        rows.append({
            "id": prop["id"],
            "name": prop["name"],
            "site_name": _own_site_name(prop),
            "slug": prop.get("slug") or "",
            "active": bool(prop["active"]),
            "is_default": prop["id"] == DEFAULT_PROPERTY_ID,
            "visible": cfg["visible"],
            "title": cfg["title"],
            "caption": cfg["caption"],
            "site_url": cfg["site_url"],
            "url": object_url(prop, cfg),
        })
    return {
        "settings": {k: settings[k] for k in ("brand", "title", "subtitle", "background_theme", "color_theme")},
        "items": rows,
        "defaults": {"brand": landlord_brand(), "title": DEFAULT_TITLE, "subtitle": DEFAULT_SUBTITLE},
    }
