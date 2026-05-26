import asyncio
import os
import json
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from handlers.admin import load_door_code
from services.booking_service import (
    init_db,
    get_booked_ranges,
    get_bookings_checkin_tomorrow,
    get_bookings_checkin_today,
    get_bookings_checkout_today,
    get_bookings_checkout_yesterday,
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
dp  = Dispatcher(storage=MemoryStorage())
dp.include_router(user_router)
dp.include_router(admin_router)

# =====================================================
# TIMEZONE — Новосибирск UTC+7
# =====================================================

NSK = timezone(timedelta(hours=7))

def now_nsk():
    return datetime.now(NSK)

# =====================================================
# HOME PAGE
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Premium Apart</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
            <style>
                body { margin:0; padding:40px; font-family:Arial; background:#f7f7f7; color:#111; }
                .card { max-width:500px; margin:auto; background:white; padding:32px; border-radius:24px; box-shadow:0 8px 24px rgba(0,0,0,0.06); }
                h1 { margin-top:0; }
                .status { color:#16a34a; font-weight:600; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🏠 Premium Apart</h1>
                <p class="status">System Online 🚀</p>
                <p>SQLite Database Connected</p>
            </div>
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
# API PRICES
# =====================================================

PRICE_FILE = "/data/prices.json"

DEFAULT_PRICES = {
    "weekday": 3500,
    "weekend": 4500,
    "cleaning": 1500
}

@app.get("/api/prices")
async def get_prices():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_PRICES

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
async def health():
    return {"status": "ok", "database": "sqlite", "app": "premium-apart"}

# =====================================================
# SCHEDULER — автоматические уведомления (время NSK)
# =====================================================

async def send_notifications():
    """Проверяем каждые 30 минут и отправляем нужные уведомления."""

    while True:

        now    = now_nsk()
        hour   = now.hour
        minute = now.minute

        try:

            # ─── 10:00 NSK — чек-лист перед выездом ───────
            if hour == 10 and minute < 30:

                bookings = get_bookings_checkout_today()

                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                f"🏠 Напоминание о выезде — сегодня до 12:00\n\n"
                                f"Пожалуйста, проверьте перед уходом:\n\n"
                                f"🔑 Оставьте ключи в почтовом ящике\n"
                                f"🔒 Закройте окна и балкон\n"
                                f"❄️ Выключите кондиционер\n"
                                f"💡 Выключите свет везде\n"
                                f"🍳 Выключите плиту и технику\n"
                                f"🗑 Вынесите мусор\n"
                                f"🛏 Сложите использованное бельё\n"
                                f"🧺 Оставьте полотенца в ванной\n"
                                f"📺 Выключите телевизор\n"
                                f"🚪 Захлопните дверь\n\n"
                                f"Спасибо что выбрали нас!\n"
                                f"Будем рады видеть снова 🤗"
                            )
                        except Exception:
                            pass

                # Уведомление администратору о выездах
                if bookings:
                    text = "🚪 Сегодня выезды:\n\n"
                    for b in bookings:
                        text += f"#{b['id']} @{b['username']} · {b['check_out']}\n"
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(admin_id, text)
                        except Exception:
                            pass

            # ─── 12:00 NSK — инструкция (за сутки до заезда) ─
            if hour == 12 and minute < 30:

                bookings  = get_bookings_checkin_tomorrow()
                door_code = load_door_code()

                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                f"🏠 Завтра ваш заезд!\n\n"
                                f"📅 {b['check_in']}\n"
                                f"📋 Бронь #{b['id']}\n\n"
                                f"━━━━━━━━━━━━━━━\n"
                                f"📍 Адрес:\n"
                                f"Улица Дачная, дом 5, квартира 286\n\n"
                                f"🔑 Ключи в почтовом ящике\n\n"
                                f"🔐 Код замка: {door_code}\n\n"
                                f"🛗 Лифт: 22 этаж\n\n"
                                f"🚪 Домофон: открою через приложение при заселении\n\n"
                                f"📱 Не забудьте прислать фото паспорта для регистрации\n\n"
                                f"💰 Полная оплата + депозит 6 000 ₽ при заселении\n\n"
                                f"📞 Возникли вопросы? Пишите сюда — на связи 🤗"
                            )
                        except Exception:
                            pass

            # ─── 15:00 NSK — приветствие в день заезда ────
            if hour == 15 and minute < 30:

                bookings = get_bookings_checkin_today()

                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                f"🎉 Добро пожаловать!\n\n"
                                f"Сегодня ваш заезд в «Городская Пауза».\n\n"
                                f"Заезд с 15:00 — квартира готова к вашему приезду.\n\n"
                                f"Если возникнут вопросы — пишите сюда, всегда на связи 🤗"
                            )
                        except Exception:
                            pass

            # ─── 14:00 NSK — просьба об отзыве (день после выезда) ─
            if hour == 14 and minute < 30:

                bookings = get_bookings_checkout_yesterday()

                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                f"🙏 Спасибо за визит!\n\n"
                                f"Надеемся, вам всё понравилось в «Городская Пауза».\n\n"
                                f"Если не сложно — оставьте отзыв, это очень помогает нам.\n\n"
                                f"Будем рады видеть вас снова! 🏠✨"
                            )
                        except Exception:
                            pass

        except Exception as e:
            print(f"⚠️ Ошибка планировщика: {e}")

        # Ждём 30 минут до следующей проверки
        await asyncio.sleep(30 * 60)


# =====================================================
# START BOT
# =====================================================

@app.on_event("startup")
async def startup():
    print("🚀 APPLICATION STARTED")
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(send_notifications())
    print("⏰ SCHEDULER STARTED (NSK UTC+7)")

# =====================================================
# SHUTDOWN
# =====================================================

@app.on_event("shutdown")
async def shutdown():
    print("🛑 APPLICATION STOPPED")
    await bot.session.close()