import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)

from config import (
    BOT_TOKEN,
    WEBAPP_URL
)

# =====================================================
# FASTAPI
# =====================================================

app = FastAPI()

# =====================================================
# TELEGRAM
# =====================================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

# =====================================================
# HTML
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <html>

        <head>
            <title>ONE APART</title>
        </head>

        <body style="font-family:Arial;padding:40px;">

            <h1>🏠 ONE APART</h1>

            <p>Новая архитектура работает</p>

        </body>

    </html>
    """

# =====================================================
# START
# =====================================================

@dp.message(CommandStart())
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
            ]

        ],

        resize_keyboard=True
    )

    await message.answer(
        "Добро пожаловать в ONE APART ✨",
        reply_markup=keyboard
    )

# =====================================================
# TELEGRAM START
# =====================================================

async def start_bot():

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(bot)

# =====================================================
# FASTAPI STARTUP
# =====================================================

@app.on_event("startup")
async def startup_event():

    asyncio.create_task(
        start_bot()
    )