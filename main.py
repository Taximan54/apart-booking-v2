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
from fastapi.responses import HTMLResponse, PlainTextResponse
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

init_db()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
dp.include_router(user_router)
dp.include_router(admin_router)

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

class ContractTemplate(BaseModel):
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

class PaymentNotify(BaseModel):
    booking_ref: str
    guest_name: str
    guest_phone: str
    guest_email: str
    total_price: int
    check_in: str
    check_out: str

# =====================================================
# CONSTANTS
# =====================================================

DATA_DIR      = "/data"
PRICE_FILE    = f"{DATA_DIR}/prices.json"
CODE_FILE     = f"{DATA_DIR}/door_code.json"
DESC_FILE     = f"{DATA_DIR}/description.txt"
DB_FILE       = f"{DATA_DIR}/bookings.db"
CONTRACT_FILE = f"{DATA_DIR}/contract_template.txt"
CONTRACT_STATIC = "static/contract_template.txt"

DEFAULT_PRICES = {"weekday": 3500, "weekend": 4500, "cleaning": 1500}

# =====================================================
# EMAIL
# =====================================================

MAIL_FROM     = os.getenv("MAIL_FROM", "citypause@mail.ru")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_ADMIN    = os.getenv("MAIL_ADMIN", "citypause@mail.ru")

def send_email(to, subject, html_body):
    if not MAIL_PASSWORD:
        print("WARNING: MAIL_PASSWORD not set")
        return
    try:
        from email.header import Header
        from email.utils import formataddr
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"]    = formataddr((str(Header("Gorodskaya Pauza", "utf-8")), MAIL_FROM))
        msg["To"]      = to
        msg["MIME-Version"] = "1.0"
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.mail.ru", 465) as server:
            server.login(MAIL_FROM, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, [to], msg.as_string())
        print("OK EMAIL sent to " + to)
    except Exception as e:
        print("ERROR email: " + str(e))

def load_contract_template():
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def fill_contract(template, data):
    for key, value in data.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template

def email_guest(booking_id, guest_name, guest_email, check_in, check_out, nights, total, prepay):
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>GORODSKAYA PAUZA</div>"
        "<div style='font-size:11px;color:#5A4A30;margin-top:6px'>APARTAMENTY POSUTOCHNO</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:16px'>BRONIROVANIE PODTVERZHDENO</div>"
        "<div style='font-size:32px;color:#C9A84C;letter-spacing:3px;margin-bottom:24px'>" + booking_id + "</div>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>Gost</td>"
        "<td style='padding:8px 0;color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>Zaezd</td>"
        "<td style='padding:8px 0;color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>Vyezd</td>"
        "<td style='padding:8px 0;color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>Nochey</td>"
        "<td style='padding:8px 0;color:#F0E6C8;font-size:12px'>" + str(nights) + "</td></tr>"
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:12px 0;color:#A89060;font-size:13px'>Itogo</td>"
        "<td style='padding:12px 0;color:#C9A84C;font-size:20px'>RUB " + str(total) + "</td></tr>"
        "<tr><td style='padding:4px 0;color:#5A4A30;font-size:12px'>Predoplata 20%</td>"
        "<td style='padding:4px 0;color:#C9A84C;font-size:13px'>RUB " + str(prepay) + "</td></tr>"
        "</table></div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>CHTO DALSHE</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.8'>"
        "1. Oplatite predoplatu 20% po ssylke T-Bank<br>"
        "2. Nazhmite Ya oplatil na sayte<br>"
        "3. Posle podtverzhdeniya poluchite kod zamka<br>"
        "4. Zaezd s 15:00, vyezd do 12:00"
        "</div></div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>"
        "citypause@mail.ru | citypause.ru"
        "</div></div>"
    )
    send_email(guest_email, "Bronirovanie " + booking_id + " — Gorodskaya Pauza", html)

def email_contract(booking_id, guest_name, guest_email, check_in, check_out, nights, total, passport=""):
    from datetime import date
    today = date.today().strftime("%d.%m.%Y")
    checkin_fmt  = datetime.strptime(check_in,  "%Y-%m-%d").strftime("%d.%m.%Y")
    checkout_fmt = datetime.strptime(check_out, "%Y-%m-%d").strftime("%d.%m.%Y")
    per_night = round(total / nights) if nights else total
    deposit = 6000

    template = load_contract_template()
    if template:
        contract_text = fill_contract(template, {
            "DATA_DOGOVORA": today,
            "FIO": guest_name,
            "PASPORT": passport or "____________",
            "ADRES": "g. Novosibirsk, ul. Dachnaya, d. 5, kv. 286, 22 etazh",
            "NOCHEY": str(nights),
            "DATA_ZAEZDA": checkin_fmt,
            "DATA_VYEZDA": checkout_fmt,
            "CENA_SUTKI": str(per_night),
            "SUMMA": str(total),
            "DEPOZIT": str(deposit),
            "NOMER_BRONI": booking_id,
        })
    else:
        contract_text = "Shablon dogovora ne nayden."

    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:24px'>"
        "<div style='font-size:24px;letter-spacing:4px;color:#C9A84C'>GORODSKAYA PAUZA</div>"
        "<div style='font-size:11px;color:#5A4A30;margin-top:4px'>DOGOVOR ARENDY</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>Bron " + booking_id + "</div>"
        "<pre style='font-size:11px;color:#A89060;line-height:1.8;white-space:pre-wrap;"
        "font-family:Arial,sans-serif'>" + contract_text + "</pre>"
        "</div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30;margin-top:24px'>"
        "citypause.ru | citypause@mail.ru"
        "</div></div>"
    )
    send_email(guest_email, "Dogovor arendy " + booking_id + " — Gorodskaya Pauza", html)

def email_admin(booking_id, guest_name, guest_phone, guest_email, check_in, check_out, nights, total, payment_method):
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='font-size:20px;color:#C9A84C;margin-bottom:24px'>NOVAYA BRON S SAYTA</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px'>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px;width:140px'>Bron</td>"
        "<td style='color:#C9A84C;font-size:13px'>" + booking_id + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Gost</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Telefon</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_phone + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Email</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_email + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Zaezd</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Vyezd</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Nochey</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + str(nights) + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Oplata</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + payment_method + "</td></tr>"
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:10px 0;color:#A89060;font-size:13px'>Summa</td>"
        "<td style='color:#C9A84C;font-size:18px'>RUB " + str(total) + "</td></tr>"
        "</table></div></div>"
    )
    send_email(MAIL_ADMIN, "Novaya bron " + booking_id + " — Gorodskaya Pauza", html)

# =====================================================
# HOME PAGE
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<html><body><h1>Gorodskaya Pauza — Online</h1></body></html>"

@app.get("/health")
async def health():
    return {"status": "ok"}

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
    return "Izyskannye apartamenty v centre goroda."

@app.post("/api/description")
async def set_description(d: Description):
    with open(DESC_FILE, "w") as f:
        f.write(d.text)
    return {"ok": True}

# =====================================================
# API — CONTRACT TEMPLATE
# =====================================================

@app.get("/api/contract-template")
async def get_contract_template():
    if os.path.exists(CONTRACT_FILE):
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    if os.path.exists(CONTRACT_STATIC):
        with open(CONTRACT_STATIC, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("Shablon dogovora ne nayden.")
@app.post("/api/contract-template")
async def set_contract_template(c: ContractTemplate):
    with open(CONTRACT_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

# =====================================================
# API — BOOKINGS
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT,
            check_in TEXT, check_out TEXT, guests INTEGER,
            status TEXT DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

@app.get("/api/bookings")
async def get_bookings(admin: Optional[str] = None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM bookings ORDER BY check_in DESC").fetchall()
    conn.close()
    bookings = [dict(r) for r in rows]

    if admin:
        return bookings

    booked = []
    checkout_dates = []
    for b in bookings:
        if b.get("status") != "cancelled":
            s = datetime.strptime(b["check_in"], "%Y-%m-%d")
            e = datetime.strptime(b["check_out"], "%Y-%m-%d")
            checkout_dates.append(b["check_out"])
            d = s
            while d < e:
                booked.append(d.strftime("%Y-%m-%d"))
                d += timedelta(days=1)
    return {"booked_dates": booked, "checkout_dates": checkout_dates}

@app.post("/api/bookings")
async def create_booking(b: BookingCreate):
    import random, string

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
            conn.execute("ALTER TABLE bookings ADD COLUMN " + col + " " + col_type)
            conn.commit()
        except Exception:
            pass

    booking_ref = "GP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    conn.execute("""
        INSERT INTO bookings (
            user_id, username, check_in, check_out, guests, status,
            guest_name, guest_phone, guest_email,
            guests_count, notes, payment_method, total_price, source
        )
        VALUES (0, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?, ?, ?, ?, 'website')
    """, (
        booking_ref, b.check_in, b.check_out, b.guests_count,
        b.guest_name, b.guest_phone, b.guest_email,
        b.guests_count, b.notes, b.payment_method, b.total_price
    ))
    conn.commit()
    conn.close()

    door_code = load_door_code()
    prepay = round(b.total_price * 0.2)

    import threading
    if b.guest_email:
        threading.Thread(target=email_guest, args=(
            booking_ref, b.guest_name, b.guest_email,
            b.check_in, b.check_out, b.nights,
            b.total_price, prepay
        ), daemon=True).start()
        threading.Thread(target=email_contract, args=(
            booking_ref, b.guest_name, b.guest_email,
            b.check_in, b.check_out, b.nights,
            b.total_price, b.passport
        ), daemon=True).start()
        threading.Thread(target=email_admin, args=(
            booking_ref, b.guest_name, b.guest_phone,
            b.guest_email, b.check_in, b.check_out,
            b.nights, b.total_price, b.payment_method
        ), daemon=True).start()

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "Novaya bron s sayta!\n\n"
                "Bron: " + booking_ref + "\n"
                "Gost: " + b.guest_name + "\n"
                "Tel: " + b.guest_phone + "\n"
                "Email: " + b.guest_email + "\n"
                "Daty: " + b.check_in + " -> " + b.check_out + "\n"
                "Summa: " + str(b.total_price) + " rub"
            )
        except Exception:
            pass

    return {"booking_id": booking_ref, "door_code": door_code, "status": "confirmed"}

@app.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: str, u: BookingUpdate):
    conn = get_db()
    conn.execute("UPDATE bookings SET status=? WHERE id=?", (u.status, booking_id))
    conn.commit()
    conn.close()
    return {"ok": True}

# =====================================================
# API — PAYMENT NOTIFY
# =====================================================

@app.post("/api/payment-notify")
async def payment_notify(p: PaymentNotify):
    prepay = round(p.total_price * 0.2)
    for admin_id in ADMIN_IDS:
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            await bot.send_message(
                admin_id,
                "Gost soobschil ob oplate (sayt)\n\n"
                "Bron: " + p.booking_ref + "\n"
                "Gost: " + p.guest_name + "\n"
                "Tel: " + p.guest_phone + "\n"
                "Email: " + p.guest_email + "\n"
                "Daty: " + p.check_in + " -> " + p.check_out + "\n"
                "Summa: " + str(p.total_price) + " rub\n"
                "Predoplata: " + str(prepay) + " rub",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="OK Podtverdit oplatu", callback_data="web_confirm_" + p.booking_ref)],
                    [InlineKeyboardButton(text="X Ne oplaceno", callback_data="web_reject_" + p.booking_ref)]
                ])
            )
        except Exception as e:
            print("Notify error: " + str(e))
    return {"ok": True}

# =====================================================
# CALLBACKS
# =====================================================

from aiogram.types import CallbackQuery

@dp.callback_query(lambda c: c.data.startswith("web_confirm_"))
async def web_payment_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_confirm_", "")
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE username=? LIMIT 1", (booking_ref,)).fetchone()
    conn.close()
    if row:
        user_id = row["user_id"] if row["user_id"] != 0 else None
        if user_id:
            try:
                await callback.bot.send_message(
                    user_id,
                    "Oplata podtverzhdena! Bron " + booking_ref + " podtverzhdena."
                )
            except Exception:
                pass
    await callback.message.edit_text(callback.message.text + "\n\nOplata podtverzhdena.")
    await callback.answer("OK!")

@dp.callback_query(lambda c: c.data.startswith("web_reject_"))
async def web_payment_reject(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_reject_", "")
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE username=? LIMIT 1", (booking_ref,)).fetchone()
    if row:
        conn.execute("UPDATE bookings SET status='cancelled' WHERE username=?", (booking_ref,))
        conn.commit()
        user_id = row["user_id"] if row["user_id"] != 0 else None
        if user_id:
            try:
                await callback.bot.send_message(user_id, "Oplata ne podtverzhdena. Bron otmenena.")
            except Exception:
                pass
    conn.close()
    await callback.message.edit_text(callback.message.text + "\n\nBron otmenena.")
    await callback.answer("Otkloneno!")

# =====================================================
# SCHEDULER
# =====================================================

async def send_notifications():
    while True:
        now    = now_nsk()
        hour   = now.hour
        minute = now.minute
        try:
            if hour == 10 and minute < 30:
                bookings = get_bookings_checkout_today()
                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                "Napominanie o vyezde — segodnya do 12:00\n\n"
                                "Pozhaluysta, proverte pered uhodom:\n"
                                "- Ostavte klyuchi v pochtovom yaschike\n"
                                "- Zakroyte okna i balkon\n"
                                "- Vyklyuchite konditsioner\n"
                                "- Vyklyuchite svet\n"
                                "- Vyklyuchite plitu i tehniku\n"
                                "- Vynesite musor\n"
                                "- Zahlopnite dver\n\n"
                                "Spasibo chto vybrali nas!"
                            )
                        except Exception:
                            pass
                if bookings:
                    text = "Segodnya vyezdy:\n\n"
                    for b in bookings:
                        text += "#" + str(b["id"]) + " @" + str(b.get("username","")) + " " + str(b["check_out"]) + "\n"
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(admin_id, text)
                        except Exception:
                            pass

            if hour == 12 and minute < 30:
                bookings  = get_bookings_checkin_tomorrow()
                door_code = load_door_code()
                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                "Zavtra vash zaezd!\n\n"
                                "Data: " + str(b["check_in"]) + "\n"
                                "Bron #" + str(b["id"]) + "\n\n"
                                "Adres: ul. Dachnaya, dom 5, kv 286\n"
                                "Lift: 22 etazh\n"
                                "Kod zamka: " + str(door_code) + "\n\n"
                                "Depozit 6000 rub pri zaselenii\n"
                                "Voprosy? Pishite syuda!"
                            )
                        except Exception:
                            pass

            if hour == 15 and minute < 30:
                bookings = get_bookings_checkin_today()
                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                "Dobro pozhalovat!\n\n"
                                "Segodnya vash zaezd v Gorodskaya Pauza.\n"
                                "Zaezd s 15:00 — kvartira gotova.\n\n"
                                "Voprosy? Pishite syuda!"
                            )
                        except Exception:
                            pass

            if hour == 14 and minute < 30:
                bookings = get_bookings_checkout_yesterday()
                for b in bookings:
                    if b["user_id"] and b["user_id"] != 0:
                        try:
                            await bot.send_message(
                                b["user_id"],
                                "Spasibo za vizit!\n\n"
                                "Nadeemsa vam vse ponravilos.\n"
                                "Budem rady videt vas snova!"
                            )
                        except Exception:
                            pass
        except Exception as e:
            print("Oshibka planirovsika: " + str(e))
        await asyncio.sleep(30 * 60)

# =====================================================
# STARTUP / SHUTDOWN
# =====================================================

@app.on_event("startup")
async def startup():
    print("APPLICATION STARTED")
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(send_notifications())
    print("SCHEDULER STARTED")

@app.on_event("shutdown")
async def shutdown():
    print("APPLICATION STOPPED")
    await bot.session.close()
