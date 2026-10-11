"""Формат iCalendar (.ics): разбор чужого календаря, сборка своего, безопасная загрузка по ссылке."""
import ipaddress
import socket
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

MAX_ICAL_BYTES = 2 * 1024 * 1024        # больше 2 МБ календарь не принимаем
FETCH_TIMEOUT = 15                      # секунд на загрузку календаря


class ICalError(Exception):
    """Календарь не удалось получить или разобрать."""


# ---------------------------------------------------------------------------
# Разбор
# ---------------------------------------------------------------------------

def _unfold(text: str) -> list:
    """Склеивает «сложенные» строки (продолжение строки начинается с пробела или табуляции)."""
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_date(value: str) -> date:
    """«20261010» или «20261010T140000Z» -> дата."""
    value = value.strip()
    try:
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except ValueError:
        raise ICalError(f"Непонятная дата в календаре: {value!r}")


def _unescape(value: str) -> str:
    return (value.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def parse_ical(text: str) -> list:
    """
    Возвращает список событий: {"uid", "start", "end", "summary", "cancelled"}.
    start — первая занятая ночь, end — день выезда (как check_in / check_out).
    События, которые не удалось разобрать, пропускаются.
    """
    if "BEGIN:VCALENDAR" not in (text or "").upper():
        raise ICalError("Это не календарь iCal (нет BEGIN:VCALENDAR)")
    events = []
    current = None
    for line in _unfold(text):
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            current = {}
            continue
        if upper == "END:VEVENT":
            if current is not None and "DTSTART" in current:
                try:
                    start = _parse_date(current["DTSTART"])
                    end = _parse_date(current["DTEND"]) if "DTEND" in current else start + timedelta(days=1)
                    if end <= start:
                        end = start + timedelta(days=1)
                    uid = (current.get("UID") or "").strip() or f"{start.isoformat()}_{end.isoformat()}"
                    events.append({
                        "uid": uid,
                        "start": start,
                        "end": end,
                        "summary": _unescape(current.get("SUMMARY", "")),
                        "cancelled": current.get("STATUS", "").strip().upper() == "CANCELLED",
                    })
                except ICalError:
                    pass
            current = None
            continue
        if current is None or ":" not in line:
            continue
        name_part, value = line.split(":", 1)
        name = name_part.split(";", 1)[0].strip().upper()
        if name in ("UID", "DTSTART", "DTEND", "SUMMARY", "STATUS") and name not in current:
            current[name] = value
    return events


# ---------------------------------------------------------------------------
# Сборка
# ---------------------------------------------------------------------------

def _escape(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r", " ").replace("\n", " "))


def _fold(line: str) -> list:
    """Складывает строку длиннее 75 байт (требование формата), не разрывая символ UTF-8."""
    out, current, size = [], "", 0
    limit = 75
    for ch in line:
        w = len(ch.encode("utf-8"))
        if size + w > limit:
            out.append(current)
            current, size, limit = " " + ch, 1 + w, 75
        else:
            current += ch
            size += w
    out.append(current)
    return out


def build_ical(events: list, calendar_name: str = "Календарь занятости", now: datetime = None) -> str:
    """
    events: [{"uid", "start": date, "end": date, "summary"}].
    Имена гостей и другие данные броней в календарь не попадают — только факт занятости.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Booking Calendar//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _escape(calendar_name),
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            "UID:" + ev["uid"],
            "DTSTAMP:" + stamp,
            "DTSTART;VALUE=DATE:" + ev["start"].strftime("%Y%m%d"),
            "DTEND;VALUE=DATE:" + ev["end"].strftime("%Y%m%d"),
            "SUMMARY:" + _escape(ev.get("summary") or "Занято"),
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        folded += _fold(line)
    return "\r\n".join(folded) + "\r\n"


# ---------------------------------------------------------------------------
# Безопасная загрузка по ссылке
# ---------------------------------------------------------------------------

def _is_public_address(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def check_calendar_url(url: str, resolve: bool = True) -> str:
    """
    Проверяет ссылку на календарь: только http/https, не адрес внутри сервера или локальной сети
    (защита от обращения к внутренним службам). Возвращает ссылку без пробелов или бросает ICalError.
    """
    url = (url or "").strip()
    if len(url) > 600:
        raise ICalError("Ссылка слишком длинная")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ICalError("Ссылка должна начинаться с http:// или https://")
    host = parsed.hostname
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal")):
        raise ICalError("Адрес календаря должен быть в интернете, а не локальным")
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if literal:
        if not _is_public_address(host):
            raise ICalError("Адрес календаря должен быть в интернете, а не локальным")
    elif resolve:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except OSError:
            raise ICalError("Не удалось найти адрес календаря в интернете")
        if not infos or not all(_is_public_address(i[4][0]) for i in infos):
            raise ICalError("Адрес календаря должен быть в интернете, а не локальным")
    return url


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Перенаправления тоже проверяются: нельзя уйти на внутренний адрес."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_calendar_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_ical(url: str) -> str:
    """Скачивает календарь по ссылке (до 2 МБ, 15 секунд). Бросает ICalError при любой проблеме."""
    url = check_calendar_url(url)
    opener = urllib.request.build_opener(_CheckedRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "BookingCalendarSync/1.0", "Accept": "text/calendar, */*"})
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read(MAX_ICAL_BYTES + 1)
    except ICalError:
        raise
    except Exception as e:
        raise ICalError(f"Не удалось скачать календарь: {e}")
    if len(data) > MAX_ICAL_BYTES:
        raise ICalError("Календарь слишком большой (больше 2 МБ)")
    return data.decode("utf-8", errors="replace")
