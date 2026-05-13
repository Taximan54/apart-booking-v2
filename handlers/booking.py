from aiogram import Router, F
from aiogram.types import Message

from services.booking_service import create_booking

router = Router()


@router.message(F.text == "/book")
async def book_handler(message: Message):

    booking_id = create_booking(
        user_id=message.from_user.id,
        username=message.from_user.username,
        date="2026-05-15",
        time="19:00",
        guests=2
    )

    await message.answer(
        f"Бронирование создано #{booking_id}"
    )