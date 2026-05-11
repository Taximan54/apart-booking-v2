import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router

# =====================================================
# FASTAPI
# =====================================================

app = FastAPI()

# =====================================================
# TELEGRAM
# =====================================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

dp.include_router(user_router)

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