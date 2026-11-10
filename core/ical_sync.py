"""
Синхронизация календарей с площадками (Авито, Яндекс Путешествия, Суточно.ру и любыми другими) по iCal.

У каждой площадки:
- своя секретная ссылка на НАШ календарь занятости (площадка подписывается на неё и закрывает у себя эти даты).
  В ней нет броней, пришедших с самой площадки, — иначе они вернулись бы к ней обратно;
- ссылка на КАЛЕНДАРЬ ПЛОЩАДКИ, который мы забираем раз в полчаса и превращаем в блокировки дат на сайте.
Брони одной площадки закрывают даты на всех остальных.
Пока в админке не указана ни одна площадка, ничего из этого не работает.

Площадки и ссылки у каждого объекта (квартиры) свои. Основной объект хранит их в прежнем файле ICAL_FILE,
остальные — в /data/properties/<номер>/ical.json. Блокировки из календаря площадки закрывают даты только
того объекта, чьей ссылкой они получены; наш календарь для площадки отдаёт только брони этого же объекта.
Везде, где есть параметр property_id, без него работает основной объект (как раньше).
"""
import asyncio
import hashlib
import json
import os
import re
import secrets
from datetime import date, datetime
from typing import Optional

from core import bookings_repo as repo
from core.constants import ICAL_FILE
from core.ical import ICalError, build_ical, check_calendar_url, fetch_ical, parse_ical
from core.landlord import get_landlord, site_url
from core.logger import get_logger
from core.properties import get_property, list_properties, property_file
from core.runtime import now_nsk
from services.booking_service import DEFAULT_PROPERTY_ID

logger = get_logger(__name__)

IMPORT_PREFIX = "ical_"                # источник блокировок, пришедших из календаря площадки: ical_<код>
MAX_PLATFORMS = 30
MAX_EVENTS = 1000
SYNC_EVERY_SECONDS = 30 * 60           # площадки обновляют календари примерно раз в час, нам хватает получаса
RESERVED_SOURCES = {"website", "admin_block", "phone", "other", "external"}

# Подсказки в админке: популярные площадки (код совпадает с источниками ручных броней)
PRESETS = [
    {"source": "avito", "name": "Авито"},
    {"source": "yandex", "name": "Яндекс Путешествия"},
    {"source": "sutochno", "name": "Суточно.ру"},
    {"source": "ostrovok", "name": "Островок"},
    {"source": "tvil", "name": "Tvil.ru"},
    {"source": "cian", "name": "Циан"},
    {"source": "booking", "name": "Booking.com"},
    {"source": "airbnb", "name": "Airbnb"},
]


class IntegrationError(Exception):
    """Ошибка в настройках площадки (понятный текст для админа)."""


# ---------------------------------------------------------------------------
# Хранение площадок
# ---------------------------------------------------------------------------

def _path(property_id: int = DEFAULT_PROPERTY_ID) -> str:
    """Файл площадок объекта: у основного — прежний ICAL_FILE, у остальных — в папке объекта."""
    return property_file(ICAL_FILE, property_id)


def _property_ids() -> list:
    """Номера всех объектов, основной первым."""
    try:
        ids = [p["id"] for p in list_properties()]
    except Exception as e:
        logger.warning("Не удалось прочитать список объектов для синхронизации календарей: %s", e)
        ids = []
    ids = [i for i in ids if i != DEFAULT_PROPERTY_ID]
    return [DEFAULT_PROPERTY_ID] + ids


def _load(property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    path = _path(property_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("platforms"), list):
                return data
        except Exception as e:
            logger.warning("Не удалось прочитать настройки синхронизации календарей: %s", e)
    return {"platforms": []}


def _save(data: dict, property_id: int = DEFAULT_PROPERTY_ID) -> None:
    with open(_path(property_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def list_platforms(property_id: int = DEFAULT_PROPERTY_ID) -> list:
    return _load(property_id)["platforms"]


def get_platform(source: str, property_id: int = DEFAULT_PROPERTY_ID) -> Optional[dict]:
    return next((p for p in list_platforms(property_id) if p["source"] == source), None)


def imported_source(source: str) -> str:
    return IMPORT_PREFIX + source


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        raise IntegrationError("Укажите название площадки")
    if len(name) > 60:
        raise IntegrationError("Название слишком длинное (макс. 60 символов)")
    return name


def add_platform(name: str, source: str = "", property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    data = _load(property_id)
    if len(data["platforms"]) >= MAX_PLATFORMS:
        raise IntegrationError(f"Можно подключить не больше {MAX_PLATFORMS} площадок")
    name = _clean_name(name)
    source = (source or "").strip().lower()
    if not source:
        source = "x" + secrets.token_hex(4)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]{1,29}", source) or source.startswith(IMPORT_PREFIX):
        raise IntegrationError("Код площадки: 2–30 символов, латиница, цифры, «-» и «_»")
    if source in RESERVED_SOURCES:
        raise IntegrationError("Этот код зарезервирован, выберите другой")
    if any(p["source"] == source for p in data["platforms"]):
        raise IntegrationError("Такая площадка уже добавлена")
    platform = {"source": source, "name": name, "url": "", "enabled": True,
                "export_token": secrets.token_urlsafe(24), "last_sync": None}
    data["platforms"].append(platform)
    _save(data, property_id)
    return platform


def update_platform(source: str, name: Optional[str] = None, url: Optional[str] = None,
                    enabled: Optional[bool] = None, property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    data = _load(property_id)
    platform = next((p for p in data["platforms"] if p["source"] == source), None)
    if not platform:
        raise IntegrationError("Площадка не найдена")
    if name is not None:
        platform["name"] = _clean_name(name)
    if url is not None:
        url = url.strip()
        if url:
            try:
                url = check_calendar_url(url)
            except ICalError as e:
                raise IntegrationError(str(e))
        platform["url"] = url
    if enabled is not None:
        platform["enabled"] = bool(enabled)
    _save(data, property_id)
    return platform


def delete_platform(source: str, property_id: int = DEFAULT_PROPERTY_ID) -> int:
    """Удаляет площадку и снимает все блокировки этого объекта, пришедшие из её календаря. Возвращает их число."""
    data = _load(property_id)
    if not any(p["source"] == source for p in data["platforms"]):
        raise IntegrationError("Площадка не найдена")
    data["platforms"] = [p for p in data["platforms"] if p["source"] != source]
    _save(data, property_id)
    return repo.cancel_all_blocks(imported_source(source), property_id)


def regenerate_token(source: str, property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    data = _load(property_id)
    platform = next((p for p in data["platforms"] if p["source"] == source), None)
    if not platform:
        raise IntegrationError("Площадка не найдена")
    platform["export_token"] = secrets.token_urlsafe(24)
    _save(data, property_id)
    return platform


def platform_by_token(token: str, property_id: int = DEFAULT_PROPERTY_ID) -> Optional[dict]:
    """Площадка объекта по секретному токену из ссылки (сравнение без утечки времени)."""
    found = None
    for p in list_platforms(property_id):
        if p.get("export_token") and secrets.compare_digest(token, p["export_token"]):
            found = p
    return found


def find_platform_by_token(token: str):
    """Ищет токен среди площадок ВСЕХ объектов. Возвращает (номер объекта, площадка) или None."""
    found = None
    for property_id in _property_ids():
        platform = platform_by_token(token, property_id)
        if platform and not found:
            found = (property_id, platform)
    return found


def export_url(platform: dict) -> str:
    return f"{site_url()}/ical/{platform['export_token']}.ics"


def _remember(source: str, report: dict, property_id: int = DEFAULT_PROPERTY_ID) -> None:
    data = _load(property_id)
    for p in data["platforms"]:
        if p["source"] == source:
            p["last_sync"] = report
            _save(data, property_id)
            return


# ---------------------------------------------------------------------------
# Наш календарь для площадки (экспорт)
# ---------------------------------------------------------------------------

def build_export_feed(source: str, today: date = None, property_id: int = DEFAULT_PROPERTY_ID) -> str:
    """
    Календарь занятости объекта для площадки source: даты броней и блокировок БЕЗ имён и других данных гостей.
    Брони самой площадки (и блокировки из её календаря) в него не входят, брони других объектов тоже.
    """
    today = today or now_nsk().date()
    domain = get_landlord()["domain"]
    events = []
    for b in repo.list_exportable(today.isoformat(), (source, imported_source(source)), property_id):
        try:
            start = datetime.strptime(b["check_in"], "%Y-%m-%d").date()
            end = datetime.strptime(b["check_out"], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        events.append({"uid": f"{b['username'] or 'id' + str(b['id'])}@{domain}", "start": start, "end": end, "summary": "Занято"})
    name = get_landlord()["brand_name"]
    if property_id != DEFAULT_PROPERTY_ID:
        prop = get_property(property_id)
        name = (prop or {}).get("name") or name
    return build_ical(events, calendar_name=name)


# ---------------------------------------------------------------------------
# Календарь площадки (импорт)
# ---------------------------------------------------------------------------

def _ref_for_uid(source: str, uid: str, property_id: int = DEFAULT_PROPERTY_ID) -> str:
    # У основного объекта номера блокировок прежние; у остальных в них входит номер объекта,
    # чтобы одинаковые события в календарях разных объектов не путались
    key = f"{source}:{uid}" if property_id == DEFAULT_PROPERTY_ID else f"{property_id}:{source}:{uid}"
    return "ICAL-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()


def sync_platform(source: str, today: date = None, fetch=None, property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    """
    Забирает календарь площадки и приводит блокировки на сайте в соответствие:
    новые брони -> блокировки, изменённые даты -> обновление, пропавшие -> блокировка снимается.
    Если календарь не скачался или не разобрался, ничего не меняется.
    """
    today = today or now_nsk().date()
    fetch = fetch or fetch_ical
    report = {"ok": False, "at": now_nsk().strftime("%Y-%m-%d %H:%M"), "created": 0, "updated": 0,
              "cancelled": 0, "skipped": 0, "error": ""}
    platform = get_platform(source, property_id)
    if not platform:
        report["error"] = "Площадка не найдена"
        return report
    if not platform["url"]:
        report["error"] = "Ссылка на календарь площадки не указана"
        _remember(source, report, property_id)
        return report
    src = imported_source(source)
    try:
        events = [e for e in parse_ical(fetch(platform["url"])) if not e["cancelled"] and e["end"] > today]
        if len(events) > MAX_EVENTS:
            raise ICalError(f"В календаре слишком много событий ({len(events)})")
    except ICalError as e:
        report["error"] = str(e)
        logger.warning("Синхронизация с «%s» (объект %s) не выполнена: %s", platform["name"], property_id, e)
        _remember(source, report, property_id)
        return report

    seen = set()
    for ev in events:
        ref = _ref_for_uid(source, ev["uid"], property_id)
        seen.add(ref)
        start, end = ev["start"].isoformat(), ev["end"].isoformat()
        nights = (ev["end"] - ev["start"]).days
        existing = repo.get_by_ref(ref)
        covering = repo.find_covering(property_id, start, end, src)
        if covering:
            # Эти даты уже заняты нашей бронью или блокировкой из другого календаря (в том числе
            # это наши же брони, вернувшиеся из площадки): новая блокировка не нужна
            if existing and existing["status"] == "blocked":
                repo.set_status_by_id(existing["id"], "cancelled")
                report["cancelled"] += 1
            else:
                report["skipped"] += 1
            continue
        if not existing:
            repo.insert_external_block(property_id, ref, start, end, nights, src,
                                       f"{platform['name']} (синхронизация календаря)")
            report["created"] += 1
        elif existing["status"] != "blocked" or existing["check_in"] != start or existing["check_out"] != end:
            repo.set_block_range(existing["id"], start, end, nights)
            report["updated"] += 1

    # Брони, которых в календаре площадки больше нет (отменены): снимаем блокировку
    for block in repo.list_active_blocks(src, today.isoformat(), property_id):
        if block["username"] not in seen:
            repo.set_status_by_id(block["id"], "cancelled")
            report["cancelled"] += 1

    report["ok"] = True
    _remember(source, report, property_id)
    logger.info("Синхронизация с «%s» (объект %s): создано %s, обновлено %s, снято %s, пропущено %s",
                platform["name"], property_id, report["created"], report["updated"], report["cancelled"], report["skipped"])
    return report


def sync_all(only_enabled: bool = True, today: date = None, fetch=None, property_id: int = DEFAULT_PROPERTY_ID) -> dict:
    """Синхронизирует все площадки ОДНОГО объекта по очереди; сбой одной не мешает остальным. Возвращает {код: отчёт}."""
    reports = {}
    for platform in list_platforms(property_id):
        if not platform["url"] or (only_enabled and not platform.get("enabled", True)):
            continue
        try:
            reports[platform["source"]] = sync_platform(platform["source"], today=today, fetch=fetch, property_id=property_id)
        except Exception as e:
            logger.error("Ошибка синхронизации «%s» (объект %s): %s", platform["name"], property_id, e, exc_info=True)
            reports[platform["source"]] = {"ok": False, "error": str(e)}
    return reports


def sync_all_properties(only_enabled: bool = True, today: date = None, fetch=None) -> dict:
    """Синхронизирует площадки всех объектов, основной первым; сбой одного объекта не мешает остальным. Возвращает {номер объекта: {код: отчёт}}."""
    result = {}
    for property_id in _property_ids():
        try:
            reports = sync_all(only_enabled, today=today, fetch=fetch, property_id=property_id)
        except Exception as e:
            logger.error("Ошибка синхронизации календарей объекта %s: %s", property_id, e, exc_info=True)
            reports = {}
        if reports:
            result[property_id] = reports
    return result


def _anything_to_sync() -> bool:
    for property_id in _property_ids():
        if any(p["url"] and p.get("enabled", True) for p in list_platforms(property_id)):
            return True
    return False


async def ical_sync_loop():
    """Фоновая задача: раз в полчаса забирает календари всех включённых площадок всех объектов."""
    await asyncio.sleep(60)   # даём приложению спокойно запуститься
    while True:
        try:
            if _anything_to_sync():
                await asyncio.to_thread(sync_all_properties)
        except Exception as e:
            logger.error("Ошибка фоновой синхронизации календарей: %s", e, exc_info=True)
        await asyncio.sleep(SYNC_EVERY_SECONDS)


def manual_booking_replaces_blocks(check_in: str, check_out: str, source: str,
                                   property_id: int = DEFAULT_PROPERTY_ID) -> int:
    """
    Ручная бронь с площадки заменяет блокировки из календаря этой площадки на те же даты
    (иначе сайт посчитал бы даты занятыми и не дал создать бронь).
    """
    if not source or source in ("phone", "other"):
        return 0
    return repo.cancel_blocks_overlapping(property_id, check_in, check_out, imported_source(source))
