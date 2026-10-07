"""Обработчики кнопок Telegram (подтверждение/отклонение оплаты)."""
import json
import os
from aiogram.types import CallbackQuery

from config import ADMIN_IDS
from core.constants import CODE_FILE
from core.bookings_repo import get_by_ref, set_status_by_ref
from core.runtime import dp
from core.signing import email_booking_confirmed
from handlers.admin import load_door_code
from core.logger import get_logger

logger = get_logger(__name__)


# =====================================================
# CALLBACKS (Telegram)
# =====================================================


@dp.callback_query(lambda c: c.data.startswith("web_confirm_"))
async def web_payment_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_confirm_", "")
    # Используем основной эндпоинт подтверждения
    booking = get_by_ref(booking_ref)
    if booking:
        booking["status"] = "confirmed"
        door_code_data = json.load(open(CODE_FILE)) if os.path.exists(CODE_FILE) else {}
        door_code = door_code_data.get("code") or load_door_code()
        set_status_by_ref(booking_ref, "confirmed")
        import threading
        if booking.get("guest_email"):
            threading.Thread(target=email_booking_confirmed, args=(booking, door_code)).start()
    try:
        await callback.message.edit_text(callback.message.text + "\n\n\u2705 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e")
    except Exception as e:
        logger.warning("Telegram: не удалось обновить сообщение: %s", e)
    await callback.answer("\u2705")

@dp.callback_query(lambda c: c.data.startswith("web_reject_"))
async def web_payment_reject(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_reject_", "")
    set_status_by_ref(booking_ref, "cancelled")
    try:
        await callback.message.edit_text(callback.message.text + "\n\n\u274c \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")
    except Exception as e:
        logger.warning("Telegram: не удалось обновить сообщение: %s", e)
    await callback.answer("\u274c")
