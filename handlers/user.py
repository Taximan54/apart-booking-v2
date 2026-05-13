import json

from aiogram import Router, types, F
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


async def send_photos(message: Message):

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

@router.message(F.text == "📸 Фото квартиры")
async def photos(message: Message):

    await send_photos(message)


# =====================================================
# DESCRIPTION
# =====================================================

@router.message(F.text == "📋 Описание квартиры")
async def description(message: Message):

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

@router.message(F.text == "🛠 Админка")
async def admin(message: Message):

    await message.answer(
        "🛠 Админка скоро будет перенесена отдельно"
    )


# =====================================================
# WEBAPP HANDLER (🔥 ВОТ ЭТО У ТЕБЯ БЫЛО СЛОМАНО)
# =====================================================

@router.message(F.web_app_data)
async def webapp_booking(message: Message):

    data = json.loads(message.web_app_data.data)

    booking_id = create_booking(
        user_id=message.from_user.id,
        username=message.from_user.username or "unknown",
        date=f"{data['check_in']} → {data['check_out']}",
        time="full_day",
        guests=int(data.get("guests", 1))
    )

    await message.answer(
        f"✅ Бронь #{booking_id}\n"
        f"📅 {data['check_in']} → {data['check_out']}\n"
        f"👥 {data['guests']} гостей"
    )

    except Exception as e:
        await message.answer(
            f"❌ Ошибка бронирования: {e}"
        )