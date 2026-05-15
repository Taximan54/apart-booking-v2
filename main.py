import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from services.booking_service import (
    init_db,
    get_booked_ranges
)


# =====================================================
# INIT DB
# =====================================================

init_db()


# =====================================================
# FASTAPI APP
# =====================================================

app = FastAPI()


# =====================================================
# STATIC FILES
# =====================================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


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

        <head>
            <title>Premium Apart</title>
        </head>

        <body style="font-family:Arial;padding:40px;">

            <h1>🏠 Premium Apart</h1>

            <p>System Online 🚀</p>

        </body>

    </html>
    """


# =====================================================
# API BOOKED DATES
# =====================================================

@app.get("/api/booked-dates")
async def booked_dates():

    return get_booked_ranges()


# =====================================================
# START BOT
# =====================================================

@app.on_event("startup")
async def startup():

    asyncio.create_task(
        dp.start_polling(bot)
    )


# =====================================================
# SHUTDOWN
# =====================================================

@app.on_event("shutdown")
async def shutdown():

    await bot.session.close()