"""Автоотмена броней с сайта, если оплата не подтверждена за заданное в админке время."""
import asyncio
import html
import json
import os
import threading
from datetime import datetime, timedelta, timezone

from core.bookings_repo import cancel_unpaid_by_id, list_expired_unpaid
from core.constants import DATA_DIR, MAIL_ADMIN
from core.logger import get_logger
from core.mailer import send_email

logger = get_logger(__name__)

PAYMENT_CONFIRM_FILE = f"{DATA_DIR}/payment_confirm.json"   # {"hours": 2}
DEFAULT_CONFIRM_HOURS = 2
MAX_CONFIRM_HOURS = 72
CHECK_EVERY_SECONDS = 300   # как часто проверяем (раз в 5 минут)


def _clamp(value) -> int:
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CONFIRM_HOURS
    return max(0, min(MAX_CONFIRM_HOURS, hours))


def get_confirm_hours() -> int:
    """Сколько часов даётся на подтверждение оплаты (0 — автоотмена выключена)."""
    try:
        with open(PAYMENT_CONFIRM_FILE, "r", encoding="utf-8") as f:
            return _clamp(json.load(f).get("hours", DEFAULT_CONFIRM_HOURS))
    except Exception:
        return DEFAULT_CONFIRM_HOURS


def set_confirm_hours(value) -> int:
    hours = _clamp(value)
    os.makedirs(os.path.dirname(PAYMENT_CONFIRM_FILE), exist_ok=True)
    with open(PAYMENT_CONFIRM_FILE, "w", encoding="utf-8") as f:
        json.dump({"hours": hours}, f)
    return hours


def _notify_admin(booking: dict, hours: int) -> None:
    def esc(key):
        return html.escape(str(booking.get(key) or ""))
    ref = booking.get("username") or booking.get("id")
    body = (
        "<div style='font-family:Arial;padding:24px;background:#0A0A0A;color:#F0E6C8'>"
        "<h2 style='color:#C9A84C'>Бронь отменена автоматически</h2>"
        f"<p>Бронь: <b>{html.escape(str(ref))}</b></p>"
        f"<p>Гость: {esc('guest_name')}, {esc('guest_phone')}</p>"
        f"<p>Даты: {esc('check_in')} — {esc('check_out')}</p>"
        f"<p>Причина: оплата не подтверждена в течение {hours} ч. Даты снова свободны на сайте.</p>"
        "</div>"
    )
    threading.Thread(target=send_email, args=(MAIL_ADMIN, f"Бронь отменена: оплата не подтверждена — {ref}", body)).start()


def run_expire() -> list:
    """Отменяет просроченные брони, возвращает список отменённых."""
    hours = get_confirm_hours()
    if hours <= 0:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    cancelled = []
    for booking in list_expired_unpaid(cutoff):
        if cancel_unpaid_by_id(booking["id"]):   # если админ успел подтвердить, бронь не тронем
            cancelled.append(booking)
            logger.info("Бронь %s отменена автоматически: оплата не подтверждена за %s ч", booking.get("username"), hours)
    for booking in cancelled:
        try:
            _notify_admin(booking, hours)
        except Exception as e:
            logger.warning("Не удалось отправить письмо об автоотмене брони: %s", e)
    return cancelled


async def expire_unpaid_loop():
    while True:
        try:
            await asyncio.to_thread(run_expire)
        except Exception as e:
            logger.error("Автоотмена неоплаченных броней: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
