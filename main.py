import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from webapp.routes import router as webapp_router

# =====================================================
# FASTAPI
# =====================================================

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(webapp_router)

# =====================================================
# TELEGRAM
# =====================================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

dp.include_router(user_router)
dp.include_router(admin_router)

# =====================================================
# START BOT
# =====================================================

async def start_bot():

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(bot)

# =====================================================
# STARTUP
# =====================================================

@app.on_event("startup")
async def startup():

    asyncio.create_task(start_bot())