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

@app.get("/", response_class=HTMLResponse)
async def home():

    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Городская Пауза</title>

        <style>

        body{
            margin:0;
            background:#f5f5f5;
            font-family:Arial;
            display:flex;
            justify-content:center;
            align-items:center;
            height:100vh;
            flex-direction:column;
        }

        h1{
            font-size:42px;
            margin-bottom:10px;
        }

        p{
            color:#666;
            margin-bottom:30px;
        }

        .btn{
            padding:18px 35px;
            background:black;
            color:white;
            border:none;
            border-radius:20px;
            font-size:20px;
            cursor:pointer;
        }

        </style>
    </head>

    <body>

        <h1>Городская Пауза</h1>

        <p>Сервис бронирования квартиры</p>

        <button class="btn">
            Календарь скоро подключим
        </button>

    </body>
    </html>
    """

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