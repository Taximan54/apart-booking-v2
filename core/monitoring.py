"""
Мониторинг сбоев: сайт сам проверяет важные вещи раз в 5 минут и пишет админу на почту.

Что проверяется:
- календари площадок (Авито, Яндекс, Суточно...): синхронизация не должна пропадать дольше N часов (по умолчанию 3);
- резервные копии: свежая копия не старше N часов (26), задан пароль для шифрования копий;
- свободное место на диске с данными (не меньше 15%);
- база данных отвечает;
- письма отправляются (последняя попытка отправки не закончилась ошибкой);
- фоновые задачи (рассылки и копии, синхронизация календарей) не завершились.

Письмо о проблеме приходит один раз, затем напоминание раз в N часов (6) и письмо «восстановлено».
Журнал инцидентов хранится в /data/incidents.json и виден в админке (раздел «Мониторинг»).
Мониторинг только читает данные и пишет письма, ничего на сайте не меняет и не удаляет.
Если упал сам сервер, письмо отправить некому: для этого нужен внешний сервис, проверяющий адрес /health/deep.
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timedelta

from core import bookings_repo as repo
from core.constants import BACKUP_DIR, DATA_DIR, LANDLORD_EMAIL
from core.ical_sync import list_platforms
from core.logger import get_logger
from core.properties import list_properties
from core.runtime import now_nsk

logger = get_logger(__name__)

SETTINGS_FILE = os.path.join(DATA_DIR, "monitoring.json")
STATE_FILE = os.path.join(DATA_DIR, "incidents.json")

DEFAULT_SETTINGS = {"enabled": True, "ical_hours": 3, "backup_hours": 26, "disk_free_percent": 15, "remind_hours": 6}
LIMITS = {"ical_hours": (1, 48), "backup_hours": (6, 96), "disk_free_percent": (5, 50), "remind_hours": (1, 72)}
CHECK_EVERY_SECONDS = 300
START_DELAY_SECONDS = 180      # даём приложению запуститься и один раз синхронизировать календари
MAX_HISTORY = 100
# Фоновые задачи, которые должны работать всё время (имя функции -> название для письма)
WATCHED_TASKS = {"send_notifications": "рассылки и резервное копирование", "ical_sync_loop": "синхронизация календарей"}

_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Хранение
# ---------------------------------------------------------------------------

def _read_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, type(default)):
                return data
        except Exception as e:
            logger.warning("Не удалось прочитать %s: %s", os.path.basename(path), e)
    return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def clean_settings(data: dict) -> dict:
    result = dict(DEFAULT_SETTINGS)
    data = data if isinstance(data, dict) else {}
    if "enabled" in data:
        result["enabled"] = bool(data["enabled"])
    for key, (low, high) in LIMITS.items():
        try:
            value = int(data.get(key, result[key]))
        except (TypeError, ValueError):
            value = result[key]
        result[key] = max(low, min(high, value))
    return result


def load_settings() -> dict:
    return clean_settings(_read_json(SETTINGS_FILE, {}))


def save_settings(changes: dict) -> dict:
    merged = clean_settings({**load_settings(), **(changes or {})})
    _write_json(SETTINGS_FILE, merged)
    return merged


def _load_state() -> dict:
    state = _read_json(STATE_FILE, {})
    state.setdefault("open", {})
    state.setdefault("history", [])
    state.setdefault("bad_since", {})
    state.setdefault("last_run", "")
    return state


def _now() -> datetime:
    return now_nsk().replace(tzinfo=None)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse(value):
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(str(value), fmt)
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Проверки (каждая возвращает список проблем: {"key", "title", "detail"})
# ---------------------------------------------------------------------------

def _grace(state: dict, keep: set, key: str, bad: bool, now: datetime, hours: float) -> bool:
    """Проблема считается настоящей, когда плохое состояние держится дольше hours часов."""
    if not bad:
        return False
    keep.add(key)
    since = _parse(state["bad_since"].get(key))
    if since is None:
        state["bad_since"][key] = _fmt(now)
        return False
    return (now - since).total_seconds() >= hours * 3600


def _disk_free_percent():
    try:
        usage = shutil.disk_usage(DATA_DIR)
        return usage.free / usage.total * 100
    except Exception as e:
        logger.warning("Не удалось узнать свободное место на диске: %s", e)
        return None


def _backup_age_hours():
    """Сколько часов назад создана самая свежая копия, или None, если копий нет. Считается по абсолютному времени, часовой пояс сервера не влияет."""
    try:
        names = [n for n in os.listdir(BACKUP_DIR) if n.startswith("backup_") and n.endswith(".zip")]
        times = [os.path.getmtime(os.path.join(BACKUP_DIR, n)) for n in names]
        return max(0.0, (time.time() - max(times)) / 3600) if times else None
    except Exception:
        return None


def _backup_password_set() -> bool:
    from core.backup import get_backup_password
    return bool(get_backup_password())


def _check_ical(settings, now, state, keep) -> list:
    problems, hours = [], settings["ical_hours"]
    for prop in list_properties():
        if not prop.get("active", True):
            continue
        for platform in list_platforms(prop["id"]):
            if not platform.get("url") or not platform.get("enabled", True):
                continue
            key = f"ical:{prop['id']}:{platform['source']}"
            title = f"Календарь «{platform['name']}» (объект «{prop['name']}») не синхронизируется"
            report = platform.get("last_sync") or {}
            if report.get("ok"):
                at = _parse(report.get("at"))
                if at and (now - at).total_seconds() >= hours * 3600:
                    problems.append({"key": key, "title": title,
                                     "detail": f"Последняя успешная синхронизация: {report['at']}. Это дольше {hours} ч."})
                continue
            why = report.get("error") or ("синхронизации ещё не было" if not report else "неизвестная ошибка")
            if _grace(state, keep, key, True, now, hours):
                problems.append({"key": key, "title": title, "detail": f"Не удаётся получить календарь дольше {hours} ч. Причина: {why}"})
    return problems


def _check_backup(settings, now, state, keep) -> list:
    problems, hours = [], settings["backup_hours"]
    age = _backup_age_hours()
    if age is None:
        if _grace(state, keep, "backup:none", True, now, hours):
            problems.append({"key": "backup:none", "title": "Нет резервных копий",
                             "detail": f"В папке копий нет ни одного файла уже больше {hours} ч."})
    elif age >= hours:
        problems.append({"key": "backup:stale", "title": "Резервная копия устарела",
                         "detail": f"Последняя копия создана примерно {_fmt(now - timedelta(hours=age))}, это {age:.0f} ч назад (порог {hours} ч)."})
    try:
        if not _backup_password_set():
            problems.append({"key": "backup:password", "title": "Не задан пароль резервных копий",
                             "detail": "Без пароля копии не шифруются и не отправляются наружу. Задайте BACKUP_PASSWORD в config.py или файл backup_password.txt."})
    except Exception as e:
        logger.warning("Не удалось проверить пароль резервных копий: %s", e)
    return problems


def _check_disk(settings) -> list:
    free = _disk_free_percent()
    if free is not None and free < settings["disk_free_percent"]:
        return [{"key": "disk:low", "title": "Мало места на диске",
                 "detail": f"Свободно {free:.1f}% (порог {settings['disk_free_percent']}%). Копии и фото могут перестать сохраняться."}]
    return []


def _check_db() -> list:
    try:
        repo.count_bookings(1)
        return []
    except Exception as e:
        return [{"key": "db:error", "title": "База данных не отвечает", "detail": str(e)[:200]}]


def _check_mail() -> list:
    from core import mailer
    status = mailer.STATUS
    if status.get("last_error_ts") and status["last_error_ts"] > status.get("last_ok_ts", 0):
        return [{"key": "mail:send", "title": "Письма не отправляются",
                 "detail": f"Последняя отправка закончилась ошибкой: {status.get('last_error', '')}"}]
    return []


def _check_tasks(task_names) -> list:
    if task_names is None:
        return []
    return [{"key": f"task:{name}", "title": f"Остановилась фоновая задача: {label}",
             "detail": "Задача завершилась из-за ошибки. Посмотрите журнал: journalctl -u apart -n 100 --no-pager, затем перезапустите сервис."}
            for name, label in WATCHED_TASKS.items() if name not in task_names]


# ---------------------------------------------------------------------------
# Письма
# ---------------------------------------------------------------------------

def alert_recipient() -> str:
    """Та же почта, что для уведомлений о бронях (notify_email в настройках сайта), иначе почта арендодателя."""
    try:
        from core.data_store import get_site_settings_dict
        email = (get_site_settings_dict().get("notify_email") or "").strip()
        if email:
            return email
    except Exception as e:
        logger.warning("Не удалось прочитать почту для уведомлений: %s", e)
    return LANDLORD_EMAIL or ""


def _brand() -> str:
    try:
        from core.landlord import get_landlord
        return get_landlord()["brand_name"]
    except Exception:
        return "Городская Пауза"


def _send_alert(kind: str, incident: dict) -> bool:
    to = alert_recipient()
    if not to:
        logger.warning("Мониторинг: не указана почта для уведомлений")
        return False
    from core import mailer
    prefix = {"open": "⚠ Проблема", "remind": "⚠ Проблема сохраняется", "resolved": "✅ Восстановлено"}[kind]
    subject = f"[{_brand()}] {prefix}: {incident['title']}"
    since = incident.get("since", "")
    lines = [incident["title"], incident.get("detail", ""), f"Началось: {since}"]
    if kind == "resolved":
        lines.append(f"Восстановлено: {incident.get('resolved', '')}")
    lines.append("Журнал: админка → Мониторинг.")
    text = "\n".join(l for l in lines if l)
    html = "<div style='font-family:Arial,sans-serif;padding:20px;color:#333'>" + "".join(
        f"<p>{l}</p>" for l in text.split("\n")) + "</div>"
    mailer.send_email(to, subject, html, text_body=text)
    return True


def send_test() -> dict:
    """Тестовое письмо: проверка, что тревоги доходят."""
    from core import mailer
    to = alert_recipient()
    if not to:
        return {"ok": False, "to": "", "error": "Не указана почта для уведомлений"}
    before = mailer.STATUS.get("last_ok_ts", 0)
    text = "Это тестовое письмо мониторинга. Если вы его получили, тревоги о сбоях будут доходить."
    mailer.send_email(to, f"[{_brand()}] Тест мониторинга", f"<p>{text}</p>", text_body=text)
    ok = mailer.STATUS.get("last_ok_ts", 0) > before
    return {"ok": ok, "to": to, "error": "" if ok else (mailer.STATUS.get("last_error") or "Письмо не отправилось")}


# ---------------------------------------------------------------------------
# Главный проход
# ---------------------------------------------------------------------------

def run_checks(task_names=None, now: datetime = None, send=None) -> dict:
    """
    Один проход проверок. task_names — имена работающих фоновых задач (None — не проверять).
    send(kind, incident) — отправка письма (в тестах подменяется). Возвращает состояние для админки.
    """
    settings = load_settings()
    state = _load_state()
    now = now or _now()
    send = send or _send_alert
    if not settings["enabled"]:
        return public_state()

    keep = set()
    problems = []
    for check in (lambda: _check_ical(settings, now, state, keep), lambda: _check_backup(settings, now, state, keep),
                  lambda: _check_disk(settings), _check_db, _check_mail, lambda: _check_tasks(task_names)):
        try:
            problems.extend(check())
        except Exception as e:   # сбой одной проверки не мешает остальным
            logger.error("Ошибка проверки мониторинга: %s", e, exc_info=True)

    def notify(kind, incident):
        try:
            send(kind, incident)
        except Exception as e:
            logger.error("Не удалось отправить письмо мониторинга: %s", e, exc_info=True)

    current = set()
    for p in problems:
        current.add(p["key"])
        incident = state["open"].get(p["key"])
        if incident is None:
            incident = {"key": p["key"], "title": p["title"], "detail": p["detail"], "since": _fmt(now), "last_notified": _fmt(now)}
            state["open"][p["key"]] = incident
            notify("open", incident)
        else:
            incident["detail"] = p["detail"]
            last = _parse(incident.get("last_notified")) or now
            if (now - last).total_seconds() >= settings["remind_hours"] * 3600:
                incident["last_notified"] = _fmt(now)
                notify("remind", incident)

    for key in list(state["open"]):
        if key not in current:
            incident = state["open"].pop(key)
            incident["resolved"] = _fmt(now)
            state["history"].append({k: incident.get(k, "") for k in ("key", "title", "detail", "since", "resolved")})
            notify("resolved", incident)
    state["history"] = state["history"][-MAX_HISTORY:]
    state["bad_since"] = {k: v for k, v in state["bad_since"].items() if k in keep}
    state["last_run"] = _fmt(now)
    _write_json(STATE_FILE, state)
    return public_state()


def public_state() -> dict:
    state = _load_state()
    return {"settings": load_settings(), "recipient": alert_recipient(), "last_run": state["last_run"],
            "open": list(state["open"].values()), "history": list(reversed(state["history"]))[:30]}


def open_incident_count() -> int:
    return len(_load_state()["open"])


def running_task_names() -> set:
    """Имена функций, чьи задачи сейчас работают (вызывать только внутри работающего цикла событий)."""
    return {getattr(t.get_coro(), "__name__", "") for t in asyncio.all_tasks()}


async def watchdog_loop():
    """Фоновая задача: раз в 5 минут запускает проверки. Любая ошибка внутри только пишется в журнал."""
    await asyncio.sleep(START_DELAY_SECONDS)
    while True:
        try:
            await asyncio.to_thread(run_checks, running_task_names())
        except Exception as e:
            logger.error("Ошибка мониторинга: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
