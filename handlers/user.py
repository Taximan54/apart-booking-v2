from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)

from config import WEBAPP_URL

router = Router()

# =====================================================
# START
# =====================================================

@router.message(CommandStart())
async def start(message: types.Message):

    keyboard = ReplyKeyboardMarkup(

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

    await message.answer(
        "Добро пожаловать в ONE APART ✨",
        reply_markup=keyboard
    )