import json
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from config import WEBAPP_URL
from services.booking_service import create_booking

router = Router()


def kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Забронировать", web_app=WebAppInfo(url=WEBAPP_URL))],
            [KeyboardButton(text="📸 Фото квартиры")],
            [KeyboardButton(text="📋 Описание квартиры")]
        ],
        resize_keyboard=True
    )


@router.message(CommandStart())
async def start(m: types.Message):
    await m.answer("🏠 Городская Пауза", reply_markup=kb())


@router.message(F.web_app_data)
async def webapp_handler(message: types.Message):

    data = json.loads(message.web_app_data.data)

    try:
        booking_id = create_booking(
            user_id=message.from_user.id,
            username=message.from_user.username or "unknown",
            check_in=data["check_in"],
            check_out=data["check_out"],
            guests=data.get("guests", 2)
        )

        await message.answer(f"✅ Бронь #{booking_id} создана")

    except Exception as e:
        await message.answer(f"❌ Ошибка бронирования: {e}")


@router.message(F.text == "📸 Фото квартиры")
async def photos(m: types.Message):
    await m.answer("📸 Фото раздел")


@router.message(F.text == "📋 Описание квартиры")
async def desc(m: types.Message):
    await m.answer("🏠 Описание квартиры")