import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

from database.models import init_db


# =====================================================
# INIT DB (ОДИН РАЗ ПРИ СТАРТЕ)
# =====================================================
init_db()


# =====================================================
# FASTAPI APP
# =====================================================
app = FastAPI()


# =====================================================
# STATIC FILES (WEBAPP + ASSETS)
# =====================================================
app.mount("/static", StaticFiles(directory="static"), name="static")


# =====================================================
# BOT INIT
# =====================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(user_router)
dp.include_router(admin_router)


# =====================================================
# ROOT PAGE (TEST)
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


# =====================================================
# START BOT (RAILWAY SAFE)
# =====================================================
@app.on_event("startup")
async def startup():
    asyncio.create_task(dp.start_polling(bot))


# =====================================================
# SHUTDOWN CLEANUP
# =====================================================
@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()