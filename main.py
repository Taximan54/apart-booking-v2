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
# FASTAPI APP
# =====================================================
app = FastAPI()


# =====================================================
# STATIC FILES (WEBAPP)
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
# ROOT TEST PAGE
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
# API: BOOKED DATES (AIRBNB FEATURE)
# =====================================================
@app.get("/api/booked-dates")
async def booked_dates():
    try:
        return JSONResponse(get_booked_dates())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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