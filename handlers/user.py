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
# PHOTO SEND
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
                )
            ],

            [
                KeyboardButton(
                    text="📋 Описание квартиры"
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
# PHOTO
# =====================================================

@router.message(lambda m: m.text == "📸 Фото квартиры")
async def photos(message: types.Message):

    await send_photos(message)


# =====================================================
# DESCRIPTION
# =====================================================

@router.message(lambda m: m.text == "📋 Описание квартиры")
async def description(message: types.Message):

    await message.answer(
        """
🏠 Городская Пауза

✨ Комфортная квартира в Новосибирске

🛏 2 гостя
📶 Wi-Fi
❄️ Кондиционер
🛁 Ванна
🍳 Кухня
📺 Smart TV

📍 Метро Заельцовская
📍 Роял Парк
📍 Центр города
"""
    )


# =====================================================
# ADMIN
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin(message: types.Message):

    await message.answer(
        "🛠 Админка скоро будет перенесена отдельно"
    )