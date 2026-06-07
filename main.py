import asyncio
import os
import json
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    passport: str = ""
    payment_method: str = "card"
    total_price: int = 0
    contract_signed: bool = False

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
CONTRACT_FILE = f"{DATA_DIR}/contract_template.txt"
CONTRACT_STATIC = "static/contract_template.txt"  # fallback из репозитория

# =====================================================
# EMAIL — отправка через mail.ru SMTP
# =====================================================

MAIL_FROM     = os.getenv("MAIL_FROM", "citypause@mail.ru")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_ADMIN    = os.getenv("MAIL_ADMIN", "citypause@mail.ru")

def send_email(to: str, subject: str, html_body: str):
    """Отправка email через mail.ru SMTP."""
    if not MAIL_PASSWORD:
        print("⚠️ MAIL_PASSWORD не задан — email не отправлен")
        return
    try:
        from email.header import Header
        from email.utils import formataddr

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"]    = formataddr((str(Header("Городская Пауза", "utf-8")), MAIL_FROM))
        msg["To"]      = to
        msg["MIME-Version"] = "1.0"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.mail.ru", 465) as server:
            server.login(MAIL_FROM, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, [to], msg.as_string())
        print(f"✅ EMAIL отправлен → {to}")
    except Exception as e:
        print(f"⚠️ Ошибка отправки email: {e}")

def fill_contract_template(template: str, data: dict) -> str:
    """Подставляет данные в плейсхолдеры шаблона."""
    for key, value in data.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template

def load_contract_template() -> str:
    """Загружает шаблон договора."""
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def email_contract(booking_id: str, guest_name: str, guest_email: str,
                   check_in: str, check_out: str, nights: int,
                   total: int, passport: str = ""):
    """Отправка договора гостю на email."""
    from datetime import date
    today = date.today().strftime("%d.%m.%Y")
    checkin_fmt  = datetime.strptime(check_in,  "%Y-%m-%d").strftime("%d.%m.%Y")
    checkout_fmt = datetime.strptime(check_out, "%Y-%m-%d").strftime("%d.%m.%Y")
    per_night = round(total / nights) if nights else total
    deposit = 6000

    template = load_contract_template()
    contract_text = fill_contract_template(template, {
        "ДАТА_ДОГОВОРА":  today,
        "АРЕНДОДАТЕЛЬ":   "Городская Пауза",
        "ФИО":            guest_name,
        "ПАСПОРТ":        passport or "____________",
        "АДРЕС":          "г. Новосибирск, ул. Дачная, д. 5, квартира 286, 22 этаж",
        "НОЧЕЙ":          str(nights),
        "ДАТА_ЗАЕЗДА":    checkin_fmt,
        "ДАТА_ВЫЕЗДА":    checkout_fmt,
        "ГОСТЕЙ":         "—",
        "ЦЕНА_СУТКИ":     f"{per_night:,}".replace(",", " "),
        "СУММА":          f"{total:,}".replace(",", " "),
        "ДЕПОЗИТ":        f"{deposit:,}".replace(",", " "),
        "EMAIL":          "citypause@mail.ru",
        "САЙТ":           "citypause.ru",
        "НОМЕР_БРОНИ":    booking_id,
    }) if template else f"""ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ ПОМЕЩЕНИЯ

def email_guest(booking_id: str, guest_name: str, guest_email: str,
                check_in: str, check_out: str, nights: int,
                total: int, prepay: int):
    """Письмо гостю — подтверждение бронирования."""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A0A0A;color:#F0E6C8;padding:40px">
      <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:28px;letter-spacing:4px;color:#C9A84C">ГОРОДСКАЯ ПАУЗА</div>
        <div style="font-size:11px;letter-spacing:3px;color:#5A4A30;margin-top:6px;text-transform:uppercase">Апартаменты посуточно</div>
      </div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px">
        <div style="font-size:13px;letter-spacing:2px;text-transform:uppercase;color:#C9A84C;margin-bottom:16px">Бронирование подтверждено</div>
        <div style="font-size:32px;color:#C9A84C;letter-spacing:3px;margin-bottom:24px">{booking_id}</div>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Гость</td><td style="padding:8px 0;color:#F0E6C8;font-size:12px">{guest_name}</td></tr>
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Заезд</td><td style="padding:8px 0;color:#F0E6C8;font-size:12px">{check_in}</td></tr>
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Выезд</td><td style="padding:8px 0;color:#F0E6C8;font-size:12px">{check_out}</td></tr>
          <tr><td style="padding:8px 0;color:#5A4A30;font-size:12px">Ночей</td><td style="padding:8px 0;color:#F0E6C8;font-size:12px">{nights}</td></tr>
          <tr style="border-top:1px solid #1E1E1E">
            <td style="padding:12px 0;color:#A89060;font-size:13px">Итого</td>
            <td style="padding:12px 0;color:#C9A84C;font-size:20px">₽{total:,}</td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#5A4A30;font-size:12px">Предоплата 20%</td>
            <td style="padding:4px 0;color:#C9A84C;font-size:13px">₽{prepay:,}</td>
          </tr>
        </table>
      </div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#C9A84C;margin-bottom:12px">Что дальше</div>
        <div style="font-size:12px;color:#A89060;line-height:1.8">
          1. Оплатите предоплату 20% по ссылке Т-Банк<br>
          2. Нажмите «Я оплатил» на сайте<br>
          3. После подтверждения вы получите код замка<br>
          4. Заезд с 15:00, выезд до 12:00
        </div>
      </div>
      <div style="text-align:center;font-size:11px;color:#5A4A30;line-height:1.8">
        По всем вопросам: <a href="mailto:citypause@mail.ru" style="color:#C9A84C">citypause@mail.ru</a><br>
        <a href="https://citypause.ru" style="color:#C9A84C">citypause.ru</a>
      </div>
    </div>
    """
    send_email(guest_email, f"Бронирование {booking_id} — Городская Пауза", html)

def email_admin(booking_id: str, guest_name: str, guest_phone: str,
                guest_email: str, check_in: str, check_out: str,
                nights: int, total: int, payment_method: str):
    """Письмо админу — новая бронь."""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A0A0A;color:#F0E6C8;padding:40px">
      <div style="font-size:20px;color:#C9A84C;margin-bottom:24px">🆕 Новая бронь с сайта</div>
      <div style="background:#141414;border:1px solid #1E1E1E;padding:24px">
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px;width:140px">Бронь</td><td style="color:#C9A84C;font-size:13px">{booking_id}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Гость</td><td style="color:#F0E6C8;font-size:12px">{guest_name}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Телефон</td><td style="color:#F0E6C8;font-size:12px">{guest_phone}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Email</td><td style="color:#F0E6C8;font-size:12px">{guest_email}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Заезд</td><td style="color:#F0E6C8;font-size:12px">{check_in}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Выезд</td><td style="color:#F0E6C8;font-size:12px">{check_out}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Ночей</td><td style="color:#F0E6C8;font-size:12px">{nights}</td></tr>
          <tr><td style="padding:6px 0;color:#5A4A30;font-size:12px">Оплата</td><td style="color:#F0E6C8;font-size:12px">{payment_method}</td></tr>
          <tr style="border-top:1px solid #1E1E1E">
            <td style="padding:10px 0;color:#A89060;font-size:13px">Сумма</td>
            <td style="color:#C9A84C;font-size:18px">₽{total:,}</td>
          </tr>
        </table>
      </div>
    </div>
    """
    send_email(MAIL_ADMIN, f"🆕 Новая бронь {booking_id} — Городская Пауза", html)

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
        # Для сайта — занятые даты + отдельно даты выезда
        # Дата выезда НЕ блокируется — выезд в 12:00, заезд в 15:00
        booked = []
        checkout_dates = []
        for b in bookings:
            if b.get("status") != "cancelled":
                s = datetime.strptime(b["check_in"], "%Y-%m-%d")
                e = datetime.strptime(b["check_out"], "%Y-%m-%d")
                checkout_dates.append(b["check_out"])
                d = s
                while d < e:
                    # check_out не добавляем в booked — она свободна для нового заезда
                    booked.append(d.strftime("%Y-%m-%d"))
                    d += timedelta(days=1)
        return {
            "booked_dates": booked,
            "checkout_dates": checkout_dates
        }

@app.post("/api/bookings")
async def create_booking(b: BookingCreate):
    import random, string

    # Реальная структура таблицы от бота:
    # id, user_id, username, check_in, check_out, guests, status, created_at
    # Добавляем недостающие колонки через ALTER TABLE

    conn = get_db()

    extra_columns = {
        "guest_name":     "TEXT DEFAULT ''",
        "guest_phone":    "TEXT DEFAULT ''",
        "guest_email":    "TEXT DEFAULT ''",
        "guests_count":   "INTEGER DEFAULT 2",
        "notes":          "TEXT DEFAULT ''",
        "payment_method": "TEXT DEFAULT 'card'",
        "total_price":    "INTEGER DEFAULT 0",
        "source":         "TEXT DEFAULT 'website'",
    }
    for col, col_type in extra_columns.items():
        try:
            conn.execute(f"ALTER TABLE bookings ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass  # колонка уже существует

    # Генерируем читаемый ID для сайта (храним в username)
    booking_ref = "ГП-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )

    conn.execute("""
        INSERT INTO bookings (
            user_id, username, check_in, check_out, guests, status,
            guest_name, guest_phone, guest_email,
            guests_count, notes, payment_method, total_price, source
        )
        VALUES (0, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?, ?, ?, ?, 'website')
    """, (
        booking_ref,
        b.check_in, b.check_out, b.guests_count,
        b.guest_name, b.guest_phone, b.guest_email,
        b.guests_count, b.notes, b.payment_method, b.total_price
    ))
    conn.commit()
    booking_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    door_code = load_door_code()
    prepay = round(b.total_price * 0.2)

    # Email — сначала, в отдельных потоках (не блокирует)
    import threading
    if b.guest_email:
        passport = getattr(b, 'passport', '')
        threading.Thread(target=email_guest, args=(
            booking_ref, b.guest_name, b.guest_email,
            b.check_in, b.check_out, b.nights,
            b.total_price, prepay
        ), daemon=True).start()
        threading.Thread(target=email_contract, args=(
            booking_ref, b.guest_name, b.guest_email,
            b.check_in, b.check_out, b.nights,
            b.total_price, passport
        ), daemon=True).start()
        threading.Thread(target=email_admin, args=(
            booking_ref, b.guest_name, b.guest_phone,
            b.guest_email, b.check_in, b.check_out,
            b.nights, b.total_price, b.payment_method
        ), daemon=True).start()

    # Telegram — после (может зависнуть из-за блокировок)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Новая бронь с сайта!\n\n"
                f"📋 {booking_ref}\n"
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

    return {"booking_id": booking_ref, "door_code": door_code, "status": "confirmed"}

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
# API — УВЕДОМЛЕНИЕ "Я ОПЛАТИЛ" С САЙТА
# =====================================================

class PaymentNotify(BaseModel):
    booking_ref:  str
    guest_name:   str
    guest_phone:  str
    guest_email:  str
    total_price:  int
    check_in:     str
    check_out:    str

@app.post("/api/payment-notify")
async def payment_notify(p: PaymentNotify):
    prepay = round(p.total_price * 0.2)

    # Отправляем уведомление всем админам с кнопками подтвердить/отклонить
    for admin_id in ADMIN_IDS:
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            await bot.send_message(
                admin_id,
                f"💳 Гость сообщил об оплате (сайт)\n\n"
                f"📋 Бронь: {p.booking_ref}\n"
                f"👤 {p.guest_name}\n"
                f"📞 {p.guest_phone}\n"
                f"📧 {p.guest_email}\n"
                f"📅 {p.check_in} → {p.check_out}\n\n"
                f"💰 Сумма: {p.total_price:,} ₽\n"
                f"💳 Ожидаем предоплату: {prepay:,} ₽\n\n"
                f"Проверьте поступление и подтвердите:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Подтвердить оплату",
                            callback_data=f"web_confirm_{p.booking_ref}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Не оплачено",
                            callback_data=f"web_reject_{p.booking_ref}"
                        )
                    ]
                ])
            )
        except Exception as e:
            print(f"Notify error: {e}")

    return {"ok": True}

# =====================================================
# API — ШАБЛОН ДОГОВОРА
# =====================================================

@app.get("/api/contract-template")
async def get_contract_template():
    # Сначала ищем в /data (редактируемый), потом в static (из репо)
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return f.read()
    return "Шаблон договора не найден. Загрузите contract_template.txt в /data/"

class ContractTemplate(BaseModel):
    text: str

@app.post("/api/contract-template")
async def set_contract_template(c: ContractTemplate):
    with open(CONTRACT_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
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


# =====================================================
# CALLBACKS — подтверждение/отклонение оплаты с сайта
# =====================================================

from aiogram.types import CallbackQuery

@dp.callback_query(lambda c: c.data.startswith("web_confirm_"))
async def web_payment_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    booking_ref = callback.data.replace("web_confirm_", "")

    # Получаем данные брони из БД
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? LIMIT 1",
        (booking_ref,)
    ).fetchone()
    conn.close()

    door_code = load_door_code()

    if row:
        guest_email = row["guest_email"] if "guest_email" in row.keys() else ""
        guest_name  = row["guest_name"]  if "guest_name"  in row.keys() else "Гость"
        check_in    = row["check_in"]
        check_out   = row["check_out"]

        # Отправляем письмо гостю если есть email (через Telegram — у нас нет smtp)
        # Уведомляем через Telegram если есть user_id
        user_id = row["user_id"] if row["user_id"] != 0 else None
        if user_id:
            try:
                await callback.bot.send_message(
                    user_id,
                    f"✅ Оплата подтверждена!\n\n"
                    f"Бронь {booking_ref} подтверждена.\n\n"
                    f"За сутки до заезда в 12:00 вы получите инструкцию по заселению с кодом замка. 🏠"
                )
            except Exception:
                pass

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ Оплата подтверждена администратором."
    )
    await callback.answer("✅ Подтверждено!")


@dp.callback_query(lambda c: c.data.startswith("web_reject_"))
async def web_payment_reject(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    booking_ref = callback.data.replace("web_reject_", "")

    # Отменяем бронь в БД
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? LIMIT 1",
        (booking_ref,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE bookings SET status='cancelled' WHERE username=?",
            (booking_ref,)
        )
        conn.commit()
        user_id = row["user_id"] if row["user_id"] != 0 else None
        if user_id:
            try:
                await callback.bot.send_message(
                    user_id,
                    f"❌ Оплата не подтверждена\n\n"
                    f"Бронь {booking_ref} отменена.\n\n"
                    f"Если это ошибка — напишите нам."
                )
            except Exception:
                pass
    conn.close()

    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ Оплата отклонена, бронь отменена."
    )
    await callback.answer("❌ Отклонено!")

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