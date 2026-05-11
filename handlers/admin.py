from aiogram import Router, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton
)

from config import ADMIN_IDS

router = Router()

# =====================================================
# АДМИНКА
# =====================================================

@router.message(lambda m: m.text == "🛠 Админка")
async def admin_panel(message: types.Message):

    if message.from_user.id not in ADMIN_IDS:
        return

    keyboard = ReplyKeyboardMarkup(

        keyboard=[

            [
                KeyboardButton(text="📋 Все брони"),
                KeyboardButton(text="📊 Статистика")
            ],

            [
                KeyboardButton(text="❌ Удалить бронь"),
                KeyboardButton(text="📅 Заблокировать даты")
            ],

            [
                KeyboardButton(text="🔓 Разблокировать даты"),
                KeyboardButton(text="💰 Изменить цену")
            ],

            [
                KeyboardButton(text="👤 Клиенты"),
                KeyboardButton(text="💬 Рассылка")
            ],

            [
                KeyboardButton(text="📈 Доход"),
                KeyboardButton(text="🕒 Последние брони")
            ],

            [
                KeyboardButton(text="🧹 Очистить брони")
            ],

            [
                KeyboardButton(text="🏠 Главное меню")
            ]

        ],

        resize_keyboard=True
    )

    await message.answer(
        "🛠 Панель администратора",
        reply_markup=keyboard
    )