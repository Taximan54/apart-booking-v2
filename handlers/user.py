from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    FSInputFile,
    InputMediaPhoto
)

from config import WEBAPP_URL

from services.booking_service import create_booking


router = Router()

# =====================================================
# PHOTOS
# =====================================================
PHOTOS = [
    "static/images/1.JPG",
    "static/images/2.JPG",
    "static/images/3.JPG"
]


async def send_photos(message: types.Message):
    media = []

    for i, photo in enumerate(PHOTOS):
        if i == 0:
            media.append(
                InputMediaPhoto(
                    media=FSInputFile(photo),
                    caption="🏠 Городская Пауза"
                )
            )
        else:
            media.append(
                InputMediaPhoto(media=FSInputFile(photo))
            )

    await message.answer_media_group(media)


# =====================================================
# KEYBOARD
# =====================================================
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📅 Забронировать",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            ],
            [
                KeyboardButton(text="📸 Фото квартиры")
            ],
            [
                KeyboardButton(text="📋 Описание квартиры")
            ],
            [
                KeyboardButton(text="🛠 Админка")
            ],
        ],
        resize_keyboard=True
    )


# =====================================================
# START
# =====================================================
@router.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "Добро пожаловать в «Городская Пауза» ✨",
        reply_markup=main_keyboard()
    )


# =====================================================
# BUTTONS (FIX — USING F.text)
# =====================================================
@router.message(F.text == "📸 Фото квартиры")
async def photos(message: types.Message):
    await send_photos(message)


@router.message(F.text == "📋 Описание квартиры")
async def description(message: types.Message):
    await message.answer(
        "🏠 Городская Пауза\n\n"
        "🛏 2 гостя\n"
        "📶 Wi-Fi\n"
        "❄️ Кондиционер\n"
        "🛁 Ванна\n"
        "🍳 Кухня\n"
        "📺 Smart TV"
    )


@router.message(F.text == "🛠 Админка")
async def admin(message: types.Message):
    await message.answer("🛠 Админка в разработке")


# =====================================================
# WEBAPP / TEST BOOKING (OPTIONAL DEBUG)
# =====================================================
@router.message()
async def test_booking(message: types.Message):
    try:
        booking_id = create_booking(
            user_id=message.from_user.id,
            username=message.from_user.username or "unknown",
            check_in="2026-05-15",
            check_out="2026-05-16",
            guests=2
        )

        await message.answer(f"✅ Booking created: {booking_id}")

    except Exception as e:
        await message.answer(f"❌ Ошибка бронирования: {e}")