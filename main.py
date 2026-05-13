import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from database.models import init_db
from services.booking_service import init_db as init_booking_db


# =====================================================
# INIT DB
# =====================================================
init_db()
init_booking_db()


# =====================================================
# APP
# =====================================================
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# =====================================================
# BOT
# =====================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(user_router)
dp.include_router(admin_router)


# =====================================================
# BOT RUNNER (CRITICAL FIX)
# =====================================================
async def start_bot():
    await dp.start_polling(bot)


# =====================================================
# STARTUP
# =====================================================
@app.on_event("startup")
async def startup():
    # важно: НЕ create_task без await защиты
    asyncio.create_task(start_bot())


# =====================================================
# SHUTDOWN
# =====================================================
@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()


# =====================================================
# ROOT
# =====================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Городская Пауза</title>
        </head>
        <body style="font-family:Arial;padding:40px;">
            <h1>🏠 Городская Пауза</h1>
            <p>Сайт работает 🚀</p>
        </body>
    </html>
    """