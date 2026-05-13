from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.booking_service import get_all_bookings


router = Router()


# =====================================================
# BOOKINGS
# =====================================================

@router.message(Command("bookings"))
async def bookings(message: Message):

    bookings = get_all_bookings()

    if not bookings:

        await message.answer(
            "❌ Бронирований нет"
        )

        return

    text = "📋 Все бронирования:\n\n"

    for booking in bookings:

        text += (
            f"ID: {booking['id']}\n"
            f"User: @{booking['username']}\n"
            f"Date: {booking['date']}\n"
            f"Time: {booking['time']}\n"
            f"Guests: {booking['guests']}\n"
            f"Status: {booking['status']}\n"
            f"-------------------\n"
        )

    await message.answer(text)