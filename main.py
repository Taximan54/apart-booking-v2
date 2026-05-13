import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from database.models import init_db
from services.booking_service import get_booked_dates


# =====================================================
# INIT DB
# =====================================================
init_db()


# =====================================================
# APP
# =====================================================
app = FastAPI()


# =====================================================
# STATIC
# =====================================================
app.mount("/static", StaticFiles(directory="static"), name="static")


# =====================================================
# BOT
# =====================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(user_router)
dp.include_router(admin_router)


# =====================================================
# HOME PAGE
# =====================================================
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head><title>Городская Пауза</title></head>
        <body style="font-family:Arial;padding:40px;">
            <h1>🏠 Городская Пауза</h1>
            <p>Сайт работает 🚀</p>
        </body>
    </html>
    """


# =====================================================
# API: BOOKED DATES
# =====================================================
@app.get("/api/booked-dates")
async def booked_dates():
    return JSONResponse(get_booked_dates())


# =====================================================
# START BOT
# =====================================================
@app.on_event("startup")
async def startup():
    asyncio.create_task(dp.start_polling(bot))


# =====================================================
# SHUTDOWN
# =====================================================
@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()