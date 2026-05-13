from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

from services.booking_service import (
    get_all_bookings,
    update_booking_status
)


router = Router()


# =====================================================
# INLINE KEYBOARD
# =====================================================

def booking_keyboard(booking_id: int):

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Confirm",
                    callback_data=f"confirm_{booking_id}"
                ),

                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"cancel_{booking_id}"
                )
            ]

        ]
    )


# =====================================================
# BOOKINGS LIST
# =====================================================

@router.message(Command("bookings"))
async def bookings(message: Message):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "❌ Бронирований нет"
        )

        return

    for booking in bookings:

        text = (
            f"📋 Бронирование #{booking['id']}\n\n"

            f"👤 User: @{booking['username']}\n"
            f"📅 Date: {booking['date']}\n"
            f"⏰ Time: {booking['time']}\n"
            f"👥 Guests: {booking['guests']}\n"
            f"📌 Status: {booking['status']}"
        )

        await message.answer(
            text,
            reply_markup=booking_keyboard(
                booking['id']
            )
        )


# =====================================================
# CONFIRM BOOKING
# =====================================================

@router.callback_query(F.data.startswith("confirm_"))
async def confirm_booking(callback: CallbackQuery):

    booking_id = int(
        callback.data.split("_")[1]
    )

    update_booking_status(
        booking_id,
        "confirmed"
    )

    await callback.message.edit_text(
        f"✅ Booking #{booking_id} confirmed"
    )

    await callback.answer()


# =====================================================
# CANCEL BOOKING
# =====================================================

@router.callback_query(F.data.startswith("cancel_"))
async def cancel_booking(callback: CallbackQuery):

    booking_id = int(
        callback.data.split("_")[1]
    )

    update_booking_status(
        booking_id,
        "cancelled"
    )

    await callback.message.edit_text(
        f"❌ Booking #{booking_id} cancelled"
    )

    await callback.answer()