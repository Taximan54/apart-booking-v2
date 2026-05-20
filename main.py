import asyncio
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from services.booking_service import (
    init_db,
    get_booked_ranges
)

# =====================================================
# INIT DATABASE
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
dp = Dispatcher(storage=MemoryStorage())
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
            <meta
                name="viewport"
                content="width=device-width, initial-scale=1.0"
            />
            <style>
                body {
                    margin: 0;
                    padding: 40px;
                    font-family: Arial;
                    background: #f7f7f7;
                    color: #111;
                }
                .card {
                    max-width: 500px;
                    margin: auto;
                    background: white;
                    padding: 32px;
                    border-radius: 24px;
                    box-shadow:
                        0 8px 24px rgba(0,0,0,0.06);
                }
                h1 {
                    margin-top: 0;
                }
                .status {
                    color: #16a34a;
                    font-weight: 600;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>
                    🏠 Premium Apart
                </h1>
                <p class="status">
                    System Online 🚀
                </p>
                <p>
                    SQLite Database Connected
                </p>
            </div>
        </body>
    </html>
    """

# =====================================================
# API BOOKED DATES
# =====================================================

@app.get("/api/booked-dates")
async def booked_dates():
    bookings = get_booked_ranges()
    return bookings

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "database": "sqlite",
        "app": "premium-apart"
    }

# =====================================================
# ⚠️ ВРЕМЕННЫЙ ЭНДПОИНТ — УДАЛИТЬ ПОСЛЕ ИСПОЛЬЗОВАНИЯ
# =====================================================

@app.get("/reset-db")
async def reset_db():
    if os.path.exists("/data/bookings.db"):
        os.remove("/data/bookings.db")
    init_db()
    return {"status": "ok", "message": "Database reset, old schema deleted"}

# =====================================================
# START BOT
# =====================================================

@app.on_event("startup")
async def startup():
    print("🚀 APPLICATION STARTED")
    asyncio.create_task(
        dp.start_polling(bot)
    )

# =====================================================
# SHUTDOWN
# =====================================================

@app.on_event("shutdown")
async def shutdown():
    print("🛑 APPLICATION STOPPED")
    await bot.session.close()