import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN

from handlers.user import router as user_router
from handlers.admin import router as admin_router

# =========================================
# APP
# =========================================

app = FastAPI()

# =========================================
# TELEGRAM
# =========================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

dp.include_router(user_router)
dp.include_router(admin_router)

# =========================================
# SITE
# =========================================

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <html>
    <head>
        <title>Городская Пауза</title>

        <style>

        body{
            background:#111;
            color:white;
            font-family:Arial;
            display:flex;
            justify-content:center;
            align-items:center;
            height:100vh;
            margin:0;
            flex-direction:column;
        }

        h1{
            font-size:52px;
            margin-bottom:10px;
        }

        p{
            color:#aaa;
            font-size:22px;
        }

        </style>

    </head>

    <body>

        <h1>Городская Пауза</h1>

        <p>
            Сервис бронирования апартаментов
        </p>

    </body>
    </html>
    """

# =========================================
# START BOT
# =========================================

async def start_bot():

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(bot)

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup():

    asyncio.create_task(start_bot())