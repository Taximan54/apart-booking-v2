import asyncio
import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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

# CORS — разрешаем запросы с сайта
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# PYDANTIC MODELS
# =====================================================

class Prices(BaseModel):
    weekday: int
    weekend: int
    cleaning: int

class DoorCode(BaseModel):
    code: str

class Description(BaseModel):
    text: str

class BookingCreate(BaseModel):
    check_in: str
    check_out: str
    nights: int
    guest_name: str
    guest_phone: str
    guest_email: str
    guests_count: int = 2
    notes: str = ""
    payment_method: str = "card"
    total_price: int = 0

class BookingUpdate(BaseModel):
    status: str

# =====================================================
# CONSTANTS
# =====================================================

DATA_DIR    = "/data"
PRICE_FILE  = f"{DATA_DIR}/prices.json"
CODE_FILE   = f"{DATA_DIR}/door_code.json"
DESC_FILE   = f"{DATA_DIR}/description.txt"
DB_FILE     = f"{DATA_DIR}/bookings.db"

DEFAULT_PRICES = {"weekday": 3500, "weekend": 4500, "cleaning": 1500}

# =====================================================
# HOME PAGE
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Городская Пауза</title>
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
                <h1>🏠 Городская Пауза</h1>
                <p class="status">System Online 🚀</p>
                <p>SQLite Database Connected</p>
            </div>
        </body>
    </html>
    """

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
async def health():
    return {"status": "ok", "database": "sqlite", "app": "gorodskaya-pauza"}

# =====================================================
# API — BOOKED DATES (старый эндпоинт, оставляем)
# =====================================================

@app.get("/api/booked-dates")
async def booked_dates():
    return get_booked_ranges()

# =====================================================
# API — PRICES
# =====================================================

@app.get("/api/prices")
async def get_prices():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_PRICES

@app.post("/api/prices")
async def set_prices(p: Prices):
    with open(PRICE_FILE, "w") as f:
        json.dump(p.dict(), f, ensure_ascii=False)
    return {"ok": True}

# =====================================================
# API — DOOR CODE
# =====================================================

@app.get("/api/door-code")
async def get_door_code():
    if os.path.exists(CODE_FILE):
        with open(CODE_FILE, "r") as f:
            return json.load(f)
    return {"code": load_door_code()}

@app.post("/api/door-code")
async def set_door_code(d: DoorCode):
    with open(CODE_FILE, "w") as f:
        json.dump({"code": d.code}, f)
    return {"ok": True}

# =====================================================
# API — DESCRIPTION
# =====================================================

@app.get("/api/description")
async def get_description():
    if os.path.exists(DESC_FILE):
        with open(DESC_FILE, "r") as f:
            return f.read()
    return "Изысканные апартаменты в центре города с дизайнерским ремонтом."

@app.post("/api/description")
async def set_description(d: Description):
    with open(DESC_FILE, "w") as f:
        f.write(d.text)
    return {"ok": True}

# =====================================================
# API — BOOKINGS
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Создаём таблицу если нет
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            check_in TEXT, check_out TEXT, nights INTEGER,
            guest_name TEXT, guest_phone TEXT, guest_email TEXT,
            guests_count INTEGER, notes TEXT,
            payment_method TEXT, total_price INTEGER,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT
        )
    """)
    conn.commit()
    return conn

@app.get("/api/bookings")
async def get_bookings(admin: Optional[str] = None):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY check_in DESC"
    ).fetchall()
    conn.close()
    bookings = [dict(r) for r in rows]

    if admin:
        # Для админки — полные данные
        return bookings
    else:
        # Для сайта — только занятые даты
        booked = []
        for b in bookings:
            if b.get("status") != "cancelled":
                s = datetime.strptime(b["check_in"], "%Y-%m-%d")
                e = datetime.strptime(b["check_out"], "%Y-%m-%d")
                d = s
                while d < e:
                    booked.append(d.strftime("%Y-%m-%d"))
                    d += timedelta(days=1)
        return {"booked_dates": booked}

@app.post("/api/bookings")
async def create_booking(b: BookingCreate):
    import random, string
    booking_id = "ГП-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )

    conn = get_db()
    conn.execute("""
        INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,'confirmed',?)
    """, (
        booking_id, b.check_in, b.check_out, b.nights,
        b.guest_name, b.guest_phone, b.guest_email,
        b.guests_count, b.notes, b.payment_method, b.total_price,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    # Уведомление администраторам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Новая бронь с сайта!\n\n"
                f"📋 #{booking_id}\n"
                f"👤 {b.guest_name}\n"
                f"📞 {b.guest_phone}\n"
                f"📧 {b.guest_email}\n"
                f"📅 {b.check_in} → {b.check_out} ({b.nights} ночей)\n"
                f"👥 Гостей: {b.guests_count}\n"
                f"💳 Оплата: {b.payment_method}\n"
                f"💰 Сумма: {b.total_price:,} ₽\n"
                f"📝 {b.notes or '—'}"
            )
        except Exception:
            pass

    door_code = load_door_code()
    return {"booking_id": booking_id, "door_code": door_code, "status": "confirmed"}

@app.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: str, u: BookingUpdate):
    conn = get_db()
    conn.execute(
        "UPDATE bookings SET status=? WHERE id=?",
        (u.status, booking_id)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

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