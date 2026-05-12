import asyncio

from fastapi import FastAPI
from database.db import init_db
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router


app = FastAPI()

init_db()

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
# WEBSITE
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <html>

        <head>
            <title>Городская Пауза</title>
        </head>

        <body style="font-family:Arial;padding:40px;">

            <h1>Городская Пауза</h1>

            <p>Сайт работает</p>

        </body>

    </html>
    """


# =====================================================
# START BOT
# =====================================================

@app.on_event("startup")
async def startup():

    asyncio.create_task(
        dp.start_polling(bot)
    )