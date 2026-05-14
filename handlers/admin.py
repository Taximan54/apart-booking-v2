from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS

from services.booking_service import (
    get_all_bookings,
    cancel_booking
)

router = Router()


# =====================================================
# ADMIN PANEL
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    kb = InlineKeyboardBuilder()

    kb.button(
        text="📋 Все брони",
        callback_data="admin_bookings"
    )

    kb.button(
        text="📅 Календарь",
        callback_data="admin_calendar"
    )

    kb.button(
        text="💰 Цены",
        callback_data="admin_prices"
    )

    kb.adjust(1)

    await message.answer(

        "🛠 ADMIN PANEL",

        reply_markup=kb.as_markup()

    )


# =====================================================
# BOOKINGS
# =====================================================

@router.callback_query(lambda c: c.data == "admin_bookings")
async def admin_bookings(callback: types.CallbackQuery):

    rows = get_all_bookings()

    if not rows:

        await callback.message.answer(
            "Броней нет"
        )

        return

    for row in rows:

        kb = InlineKeyboardBuilder()

        kb.button(
            text="❌ Отменить",
            callback_data=f"cancel_{row[0]}"
        )

        text = f"""
🏠 BOOKING #{row[0]}

👤 {row[1]}
📅 {row[2]} → {row[3]}
👥 {row[4]}
📌 {row[5]}
"""

        await callback.message.answer(

            text,

            reply_markup=kb.as_markup()

        )


# =====================================================
# CANCEL
# =====================================================

@router.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel(callback: types.CallbackQuery):

    booking_id = int(
        callback.data.split("_")[1]
    )

    cancel_booking(booking_id)

    await callback.message.answer(
        f"❌ Бронь #{booking_id} отменена"
    )