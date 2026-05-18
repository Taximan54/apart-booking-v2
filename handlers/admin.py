from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup
from aiogram.types import InlineKeyboardButton
from aiogram.filters import Command

from services.booking_service import (
    get_all_bookings,
    cancel_booking
)

router = Router()


# =====================================================
# ADMIN BUTTON
# =====================================================

ADMIN_PASSWORD = "1234"


# =====================================================
# ADMIN PANEL
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "Броней пока нет"
        )

        return

    text = "📋 Все брони:\n\n"

    keyboard = []

    for row in bookings:

        booking_id = row["id"]

        username = row["username"]

        check_in = row["check_in"]

        check_out = row["check_out"]

        status = row["status"]

        text += (
            f"#{booking_id} | "
            f"{check_in} → {check_out}\n"
            f"👤 @{username}\n"
            f"📌 {status}\n\n"
        )

        if status != "cancelled":

            keyboard.append([

                InlineKeyboardButton(
                    text=f"❌ Отменить #{booking_id}",
                    callback_data=f"cancel_{booking_id}"
                )

            ])

    markup = InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )

    await message.answer(
        text,
        reply_markup=markup
    )


# =====================================================
# CANCEL BOOKING
# =====================================================

@router.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel_booking_handler(
    callback: types.CallbackQuery
):

    booking_id = int(
        callback.data.split("_")[1]
    )

    cancel_booking(booking_id)

    await callback.answer(
        "Бронь отменена"
    )

    await callback.message.edit_text(
        f"❌ Бронь #{booking_id} отменена"
    )


# =====================================================
# ADMIN CALENDAR
# =====================================================

@router.message(Command("calendar"))
async def admin_calendar(message: types.Message):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "Броней нет"
        )

        return

    text = "📅 Календарь броней:\n\n"

    for row in bookings:

        text += (
            f"#{row['id']} | "
            f"{row['check_in']} → "
            f"{row['check_out']} | "
            f"{row['status']}\n"
        )

    await message.answer(text)