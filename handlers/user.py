import json

from aiogram import Router, types
from aiogram.filters import CommandStart

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    FSInputFile,
    InputMediaPhoto,
    Message
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


# =====================================================
# PHOTO SENDER
# =====================================================

async def send_photos(message):

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
                InputMediaPhoto(
                    media=FSInputFile(photo)
                )
            )

    await message.answer_media_group(media)


# =====================================================
# MAIN KEYBOARD
# =====================================================

def main_keyboard():

    return ReplyKeyboardMarkup(

        keyboard=[

            [
                KeyboardButton(
                    text="📅 Забронировать",
                    web_app=WebAppInfo(
                        url=WEBAPP_URL
                    )
                )
            ],

            [
                KeyboardButton(
                    text="📸 Фото квартиры"
                ),

                KeyboardButton(
                    text="📋 Описание"
                )
            ],

            [
                KeyboardButton(
                    text="🛠 Админка"
                )
            ]

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
# PHOTOS
# =====================================================

@router.message(lambda m: m.text == "📸 Фото квартиры")
async def photos(message: types.Message):

    await send_photos(message)


# =====================================================
# DESCRIPTION
# =====================================================

@router.message(lambda m: m.text == "📋 Описание")
async def description(message: types.Message):

    await message.answer(
        """
🏠 Городская Пауза

✨ Комфортная квартира

🛏 2 гостя
📶 Wi-Fi
❄️ Кондиционер
🛁 Ванна
🍳 Кухня
📺 Smart TV
"""
    )


# =====================================================
# WEBAPP BOOKING
# =====================================================

@router.message(lambda m: m.web_app_data)
async def webapp_booking(message: Message):

    try:

        data = json.loads(
            message.web_app_data.data
        )

        booking_id = create_booking(

            user_id=message.from_user.id,

            username=message.from_user.username or "unknown",

            check_in=data["check_in"],

            check_out=data["check_out"],

            guests=data.get("guests", 2)
        )

        await message.answer(
            f"""
✅ Бронь #{booking_id}

📅 {data['check_in']} → {data['check_out']}
👥 {data.get('guests', 2)} гостей
"""
        )

    except Exception as e:

        await message.answer(
            f"❌ Ошибка бронирования: {e}"
        )