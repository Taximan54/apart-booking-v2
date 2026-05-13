import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from services.booking_service import init_db, get_booked_ranges


# =====================================================
# INIT DB
# =====================================================
init_db()


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
# API FOR CALENDAR
# =====================================================
@app.get("/api/booked-dates")
async def booked_dates():
    return get_booked_ranges()


# =====================================================
# START BOT
# =====================================================
@app.on_event("startup")
async def startup():
    asyncio.create_task(dp.start_polling(bot))


@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()