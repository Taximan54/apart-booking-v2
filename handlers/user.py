import json

from aiogram import Router, types, F
from aiogram.types import Message

from services.booking_service import create_booking

router = Router()


@router.message(F.web_app_data)
async def webapp_booking(message: Message):

    try:
        data = json.loads(message.web_app_data.data)

        booking_id = create_booking(
            user_id=message.from_user.id,
            username=message.from_user.username or "unknown",
            check_in=data["check_in"],
            check_out=data["check_out"],
            guests=int(data.get("guests", 1))
        )

        await message.answer(
            f"✅ Бронь #{booking_id}\n"
            f"📅 {data['check_in']} → {data['check_out']}\n"
            f"👥 {data['guests']} гостей"
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка бронирования: {str(e)}")