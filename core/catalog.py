"""
Каталог апартаментов: страница «Все апартаменты» (/apartments), на которой гость выбирает квартиру.

Каталог всегда синхронизирован с объектами: список берётся из реестра объектов, поэтому новый объект
появляется в каталоге сам, а удалённый или отключённый исчезает. Отдельно хранятся только настройки каталога
(тексты страницы, оформление, шрифты, сетка и по каждому объекту: показывать ли, название, подпись, свой адрес сайта, порядок)
в /data/catalog.json. Они общие для всех объектов.
"""
import json
import os
import re
from urllib.parse import quote

from core.constants import DATA_DIR, DEFAULT_PRICES, PRICE_FILE, SETTINGS_FILE
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

DEFAULT_BUTTON_LABEL = "Квартиры"   # название кнопки перехода в каталог на страницах сайта
MAX_BUTTON_LABEL = 30
DEFAULT_BUTTON_SCALE = 1.0   # размер шрифта кнопки перехода в каталог (масштаб)
COLUMNS = ("auto", "1", "2", "3", "4")   # сетка карточек на компьютере: сколько в ряд

# Шрифты каталога (все с поддержкой кириллицы). Ключи совпадают с ключами шрифтов сайта в «Настройках сайта»;
# montserrat — спокойный шрифт без засечек. Группы: шапка, заголовок, подзаголовок, названия квартир, текст в карточках.
FONT_KEYS = ("cormorant", "im_fell", "unifraktur", "tangerine", "pacifico", "berkshire", "poiret", "montserrat")
FONT_DEFAULTS = {"brand": "cormorant", "title": "cormorant", "subtitle": "montserrat", "card": "cormorant", "text": "montserrat"}
FONT_GROUPS_WITH_BOLD = ("brand", "title", "subtitle", "card")
MIN_SCALE, MAX_SCALE = 0.5, 2.5

MAX_PHOTOS = 12
MAX_AMENITIES = 6
MAX_CAPTION = 200


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
        "caption": text("caption", MAX_CAPTION),
        "site_url": text("site_url", 300),
    }


def _clean_fonts(raw, strict: bool = False) -> dict:
    """Шрифты каталога: для каждой группы шрифт (пусто — по умолчанию), жирность и размер (масштаб)."""
    raw = raw if isinstance(raw, dict) else {}
    result = {}
    for group in FONT_DEFAULTS:
        font = str(raw.get(f"{group}_font") or "").strip()
        if font and font not in FONT_KEYS:
            if strict:
                raise CatalogError("Неизвестный шрифт")
            font = ""
        try:
            scale = float(raw.get(f"{group}_scale") or 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        if not MIN_SCALE <= scale <= MAX_SCALE:
            if strict:
                raise CatalogError("Размер шрифта должен быть от 0,5 до 2,5")
            scale = 1.0
        result[f"{group}_font"] = font
        result[f"{group}_scale"] = round(scale, 2)
        if group in FONT_GROUPS_WITH_BOLD:
            result[f"{group}_bold"] = bool(raw.get(f"{group}_bold"))
    return result


def _resolved_fonts(fonts: dict) -> dict:
    """Шрифты для страницы: пустой шрифт заменяется шрифтом по умолчанию."""
    resolved = dict(fonts)
    for group, default in FONT_DEFAULTS.items():
        resolved[f"{group}_font"] = fonts.get(f"{group}_font") or default
    return resolved


def _clean_button_scale(value) -> float:
    try:
        scale = float(value or DEFAULT_BUTTON_SCALE)
    except (TypeError, ValueError):
        return DEFAULT_BUTTON_SCALE
    return round(scale, 2) if MIN_SCALE <= scale <= MAX_SCALE else DEFAULT_BUTTON_SCALE


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
    columns = str(data.get("columns") or "auto")
    return {
        "button_label": str(data.get("button_label") or "").strip()[:MAX_BUTTON_LABEL],
        "button_scale": _clean_button_scale(data.get("button_scale")),
        "columns": columns if columns in COLUMNS else "auto",
        "fonts": _clean_fonts(data.get("fonts")),
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


def save_catalog_settings(brand, title, subtitle, background_theme, color_theme, items, button_label="", columns="auto", fonts=None, button_scale=1.0) -> dict:
    brand, title, subtitle = (brand or "").strip(), (title or "").strip(), (subtitle or "").strip()
    if len(brand) > 80:
        raise CatalogError("Название сети слишком длинное (макс. 80 символов)")
    if len(title) > 100:
        raise CatalogError("Заголовок слишком длинный (макс. 100 символов)")
    if len(subtitle) > 300:
        raise CatalogError("Подзаголовок слишком длинный (макс. 300 символов)")
    button_label = (button_label or "").strip()
    if len(button_label) > MAX_BUTTON_LABEL:
        raise CatalogError(f"Название кнопки слишком длинное (макс. {MAX_BUTTON_LABEL} символов)")
    try:
        button_scale = float(button_scale or DEFAULT_BUTTON_SCALE)
    except (TypeError, ValueError):
        raise CatalogError("Неверный размер шрифта кнопки")
    if not MIN_SCALE <= button_scale <= MAX_SCALE:
        raise CatalogError("Размер шрифта кнопки должен быть от 0,5 до 2,5")
    columns = str(columns or "auto")
    if columns not in COLUMNS:
        raise CatalogError("Неизвестный вариант сетки")
    if fonts is not None and not isinstance(fonts, dict):
        fonts = fonts.model_dump() if hasattr(fonts, "model_dump") else fonts.dict()
    clean_fonts = _clean_fonts(fonts, strict=True)
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
        if len(row["caption"]) > MAX_CAPTION:
            raise CatalogError(f"Подпись слишком длинная (макс. {MAX_CAPTION} символов)")
        _check_site_url(row["site_url"])
        clean.append(row)
    data = {"brand": brand, "title": title, "subtitle": subtitle, "background_theme": background_theme or "",
            "color_theme": color_theme or "", "button_label": button_label, "button_scale": round(button_scale, 2), "columns": columns, "fonts": clean_fonts, "items": clean}
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
        "button_label": settings["button_label"] or DEFAULT_BUTTON_LABEL,
        "button_scale": settings["button_scale"],
        "columns": settings["columns"],
        "fonts": _resolved_fonts(settings["fonts"]),
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
        "settings": {k: settings[k] for k in ("brand", "title", "subtitle", "background_theme", "color_theme", "button_label", "button_scale", "columns", "fonts")},
        "items": rows,
        "defaults": {"brand": landlord_brand(), "title": DEFAULT_TITLE, "subtitle": DEFAULT_SUBTITLE,
                     "button_label": DEFAULT_BUTTON_LABEL, "fonts": _resolved_fonts(_clean_fonts({}))},
    }
