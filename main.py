import asyncio
import os
import json
import sqlite3
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, date, timezone, timedelta
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
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

class PromoCodes(BaseModel):
    codes: Dict[str, int]   # {"SUMMER10": 10} — код -> процент скидки

class PromoValidate(BaseModel):
    code: str

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
    payment_method: str = "tbank"
    total_price: int = 0
    contract_signed: bool = False
    promo_code: str = ""

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

DATA_DIR         = "/data"
PRICE_FILE       = f"{DATA_DIR}/prices.json"
PROMO_FILE       = f"{DATA_DIR}/promo_codes.json"
CODE_FILE        = f"{DATA_DIR}/door_code.json"
DESC_FILE        = f"{DATA_DIR}/description.txt"
DB_FILE          = f"{DATA_DIR}/bookings.db"
CONTRACT_FILE    = f"{DATA_DIR}/contract_template.txt"
CONTRACT_STATIC  = "static/contract_template.txt"
CONTRACTS_DIR    = f"{DATA_DIR}/contracts"
DEFAULT_PRICES   = {"weekday": 3500, "weekend": 4500, "cleaning": 1500}

os.makedirs(CONTRACTS_DIR, exist_ok=True)

# =====================================================
# EMAIL
# =====================================================

MAIL_FROM     = os.getenv("MAIL_FROM", "citypause@mail.ru")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_ADMIN    = os.getenv("MAIL_ADMIN", "citypause@mail.ru")

def send_email(to, subject, html_body, attachments=None):
    """
    attachments: список словарей [{"filename": "dogovor_123.txt", "content": "...текст..."}]
    Текстовые вложения кодируются в UTF-8 и прикрепляются как отдельный .txt файл,
    чтобы длинный договор не обрезался почтовым клиентом при показе тела письма.
    """
    if not MAIL_PASSWORD:
        print("WARNING: MAIL_PASSWORD not set")
        return
    try:
        from email.header import Header
        from email.utils import formataddr
        msg = MIMEMultipart("mixed")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"]    = formataddr((str(Header("Gorodskaya Pauza", "utf-8")), MAIL_FROM))
        msg["To"]      = to
        msg["MIME-Version"] = "1.0"

        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(body_part)

        for att in (attachments or []):
            filename = att.get("filename", "attachment.txt")
            content  = att.get("content", "")
            part = MIMEBase("application", "octet-stream")
            part.set_payload(content.encode("utf-8"))
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.mail.ru", 465) as server:
            server.login(MAIL_FROM, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM, [to], msg.as_string())
        print("OK EMAIL sent to " + to)
    except Exception as e:
        print("ERROR email: " + str(e))

# =====================================================
# CONTRACT
# =====================================================

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

def generate_contract(booking):
    """Генерирует текст договора из шаблона и данных брони."""
    today        = date.today().strftime("%d.%m.%Y")
    checkin_fmt  = datetime.strptime(booking["check_in"],  "%Y-%m-%d").strftime("%d.%m.%Y")
    checkout_fmt = datetime.strptime(booking["check_out"], "%Y-%m-%d").strftime("%d.%m.%Y")
    nights       = booking.get("nights") or booking.get("guests", 1)
    total        = booking.get("total_price", 0)
    discount_pct = booking.get("discount_percent", 0) or 0
    # total_price уже учитывает скидку по промокоду — для "цены за ночь" в договоре
    # восстанавливаем исходную (до скидки) сумму, чтобы тариф совпадал с тем, что гость видел при выборе дат
    pre_discount_total = round(total / (1 - discount_pct / 100)) if discount_pct else total
    per_night    = round(pre_discount_total / nights) if nights else pre_discount_total

    template = load_contract_template()
    if not template:
        return "Shablon dogovora ne nayden."

    return fill_contract(template, {
        "ДАТА_ДОГОВОРА":  today,
        "АРЕНДОДАТЕЛЬ":   "Городская Пауза",
        "ФИО":            booking.get("guest_name", ""),
        "ПАСПОРТ":        booking.get("passport", "____________"),
        "АДРЕС":          "г. Новосибирск, ул. Дачная, д. 5, квартира 286, 22 этаж",
        "НОЧЕЙ":          str(nights),
        "ДАТА_ЗАЕЗДА":    checkin_fmt,
        "ДАТА_ВЫЕЗДА":    checkout_fmt,
        "ГОСТЕЙ":         str(booking.get("guests_count", booking.get("guests", 2))),
        "ЦЕНА_В_СУТКИ":   str(per_night),
        "ИТОГО":          str(total),
        "ДЕПОЗИТ":        "6 000",
        "EMAIL":          "citypause@mail.ru",
        "САЙТ":           "citypause.ru",
        "НОМЕР_БРОНИ":    str(booking.get("username") or booking.get("id", "")),
        # Также поддерживаем латинские плейсхолдеры
        "DATA_DOGOVORA":  today,
        "FIO":            booking.get("guest_name", ""),
        "PASPORT":        booking.get("passport", "____________"),
        "ADRES":          "g. Novosibirsk, ul. Dachnaya, d. 5, kv. 286, 22 etazh",
        "NOCHEY":         str(nights),
        "DATA_ZAEZDA":    checkin_fmt,
        "DATA_VYEZDA":    checkout_fmt,
        "GOSTEY":         str(booking.get("guests_count", 2)),
        "CENA_SUTKI":     str(per_night),
        "SUMMA":          str(total),
        "DEPOZIT":        "6000",
        "NOMER_BRONI":    str(booking.get("username") or booking.get("id", "")),
    })

def save_contract(booking_ref, contract_text):
    """Сохраняет договор в файл."""
    path = os.path.join(CONTRACTS_DIR, booking_ref + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(contract_text)
    return path

# =====================================================
# EMAIL FUNCTIONS
# =====================================================

def email_booking_created(booking_id, guest_name, guest_email, check_in, check_out, nights, total, prepay):
    """Письмо гостю — бронь создана, ожидаем оплату."""
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "<div style='font-size:11px;color:#5A4A30;margin-top:6px'>"
        "\u0410\u043f\u0430\u0440\u0442\u0430\u043c\u0435\u043d\u0442\u044b \u043f\u043e\u0441\u0443\u0442\u043e\u0447\u043d\u043e</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:13px;color:#C9A84C;margin-bottom:8px'>"
        "\u0411\u0420\u041e\u041d\u042c \u0421\u041e\u0417\u0414\u0410\u041d\u0410</div>"
        "<div style='font-size:32px;color:#C9A84C;letter-spacing:3px;margin-bottom:24px'>"
        + booking_id + "</div>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0413\u043e\u0441\u0442\u044c</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u041d\u043e\u0447\u0435\u0439</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + str(nights) + "</td></tr>"
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:12px 0;color:#A89060;font-size:13px'>"
        "\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c</td>"
        "<td style='padding:12px 0;color:#C9A84C;font-size:20px'>"
        + str(total) + " \u20bd</td></tr>"
        "<tr><td style='padding:4px 0;color:#5A4A30;font-size:12px'>"
        "\u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 20%</td>"
        "<td style='color:#C9A84C;font-size:13px'>" + str(prepay) + " \u20bd</td></tr>"
        "</table></div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>"
        "\u0427\u0422\u041e \u0414\u0410\u041b\u042c\u0428\u0415</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.8'>"
        "1. \u041e\u043f\u043b\u0430\u0442\u0438\u0442\u0435 \u043f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0443 20% \u043f\u043e \u0441\u0441\u044b\u043b\u043a\u0435 \u0422-\u0411\u0430\u043d\u043a<br>"
        "2. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u042f \u043e\u043f\u043b\u0430\u0442\u0438\u043b\u00bb \u043d\u0430 \u0441\u0430\u0439\u0442\u0435<br>"
        "3. \u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442 \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442 \u0434\u043e\u0433\u043e\u0432\u043e\u0440 + \u043a\u043e\u0434 \u0437\u0430\u043c\u043a\u0430<br>"
        "4. \u0417\u0430\u0435\u0437\u0434 \u0441 15:00, \u0432\u044b\u0435\u0437\u0434 \u0434\u043e 12:00"
        "</div></div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>"
        "citypause@mail.ru | citypause.ru</div></div>"
    )
    send_email(guest_email,
               "\u0411\u0440\u043e\u043d\u044c " + booking_id + " \u2014 \u0413\u043e\u0440\u043e\u0434\u0441\u043a\u0430\u044f \u041f\u0430\u0443\u0437\u0430",
               html)

def email_booking_confirmed(booking, door_code):
    """Письмо гостю — оплата подтверждена, договор + код замка."""
    guest_email  = booking.get("guest_email", "")
    guest_name   = booking.get("guest_name", "")
    booking_ref  = str(booking.get("username") or booking.get("id", ""))
    check_in     = booking.get("check_in", "")
    check_out    = booking.get("check_out", "")

    contract_text = generate_contract(booking)
    save_contract(booking_ref, contract_text)
    contract_filename = f"dogovor_{booking_ref}.txt"

    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='text-align:center;margin-bottom:32px'>"
        "<div style='font-size:28px;letter-spacing:4px;color:#C9A84C'>"
        "\u0413\u041e\u0420\u041e\u0414\u0421\u041a\u0410\u042f \u041f\u0410\u0423\u0417\u0410</div>"
        "</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:32px;margin-bottom:24px'>"
        "<div style='font-size:16px;color:#C9A84C;margin-bottom:16px'>"
        "\u2705 \u041e\u043f\u043b\u0430\u0442\u0430 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430!</div>"
        "<div style='font-size:13px;color:#A89060;margin-bottom:24px'>"
        "\u0411\u0440\u043e\u043d\u044c " + booking_ref + "</div>"
        "<div style='background:#0A0A0A;border:1px solid rgba(201,168,76,0.3);padding:20px;margin-bottom:16px;text-align:center'>"
        "<div style='font-size:11px;color:#5A4A30;margin-bottom:8px'>"
        "\u041a\u041e\u0414 \u0417\u0410\u041c\u041a\u0410</div>"
        "<div style='font-size:36px;color:#C9A84C;letter-spacing:8px;font-weight:bold'>"
        + str(door_code) + "</div>"
        "</div>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + " \u0441 15:00</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + " \u0434\u043e 12:00</td></tr>"
        "<tr><td style='padding:8px 0;color:#5A4A30;font-size:12px'>"
        "\u0410\u0434\u0440\u0435\u0441</td>"
        "<td style='color:#F0E6C8;font-size:12px'>"
        "\u0443\u043b. \u0414\u0430\u0447\u043d\u0430\u044f, \u0434. 5, \u043a\u0432. 286, 22 \u044d\u0442\u0430\u0436</td></tr>"
        "</table></div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:24px'>"
        "<div style='font-size:11px;color:#C9A84C;margin-bottom:12px'>"
        "\u0414\u041e\u0413\u041e\u0412\u041e\u0420 \u0410\u0420\u0415\u041d\u0414\u042b</div>"
        "<div style='font-size:12px;color:#A89060;line-height:1.7'>"
        "\u041f\u043e\u043b\u043d\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d \u043a \u044d\u0442\u043e\u043c\u0443 \u043f\u0438\u0441\u044c\u043c\u0443 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u043c \u0444\u0430\u0439\u043b\u043e\u043c " + contract_filename + " \u2014 \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u0435, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0442\u044c \u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0434\u043e\u0433\u043e\u0432\u043e\u0440.</div>"
        "</div>"
        "<div style='text-align:center;font-size:11px;color:#5A4A30'>"
        "citypause@mail.ru | citypause.ru</div></div>"
    )
    send_email(guest_email,
               "\u0411\u0440\u043e\u043d\u044c \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430 \u2014 " + booking_ref,
               html,
               attachments=[{"filename": contract_filename, "content": contract_text}])

def email_admin_new_booking(booking_id, guest_name, guest_phone, guest_email,
                             check_in, check_out, nights, total,
                             promo_code="", discount_percent=0):
    """Письмо админу — новая бронь ожидает подтверждения."""
    promo_row = ""
    if promo_code:
        promo_row = (
            "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
            "\u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434</td>"
            "<td style='color:#C9A84C;font-size:12px'>" + promo_code +
            " (\u2212" + str(discount_percent) + "%)</td></tr>"
        )
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"
        "background:#0A0A0A;color:#F0E6C8;padding:40px'>"
        "<div style='font-size:18px;color:#C9A84C;margin-bottom:8px'>"
        "\u041d\u043e\u0432\u0430\u044f \u0431\u0440\u043e\u043d\u044c \u0441 \u0441\u0430\u0439\u0442\u0430</div>"
        "<div style='font-size:13px;color:#5A4A30;margin-bottom:24px'>"
        "\u041e\u0436\u0438\u0434\u0430\u0435\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \u043e\u043f\u043b\u0430\u0442\u044b</div>"
        "<div style='background:#141414;border:1px solid #1E1E1E;padding:24px;margin-bottom:16px'>"
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px;width:140px'>"
        "\u0411\u0440\u043e\u043d\u044c</td>"
        "<td style='color:#C9A84C;font-size:13px'>" + booking_id + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0413\u043e\u0441\u0442\u044c</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_name + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0422\u0435\u043b\u0435\u0444\u043e\u043d</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_phone + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>Email</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + guest_email + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0417\u0430\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_in + "</td></tr>"
        "<tr><td style='padding:6px 0;color:#5A4A30;font-size:12px'>"
        "\u0412\u044b\u0435\u0437\u0434</td>"
        "<td style='color:#F0E6C8;font-size:12px'>" + check_out + "</td></tr>"
        + promo_row +
        "<tr style='border-top:1px solid #1E1E1E'>"
        "<td style='padding:10px 0;color:#A89060;font-size:13px'>"
        "\u0421\u0443\u043c\u043c\u0430</td>"
        "<td style='color:#C9A84C;font-size:18px'>" + str(total) + " \u20bd</td></tr>"
        "</table></div>"
        "<div style='padding:16px;background:rgba(201,168,76,0.05);border:1px solid rgba(201,168,76,0.2);font-size:12px;color:#A89060'>"
        "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u043e\u043f\u043b\u0430\u0442\u0443 \u0432 \u0430\u0434\u043c\u0438\u043d\u043a\u0435: "
        "<a href='https://citypause.ru/static/admin.html' style='color:#C9A84C'>"
        "citypause.ru/static/admin.html</a>"
        "</div></div>"
    )
    send_email(MAIL_ADMIN,
               "\u041d\u043e\u0432\u0430\u044f \u0431\u0440\u043e\u043d\u044c " + booking_id + " \u2014 \u0416\u0434\u0451\u0442 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f",
               html)

# =====================================================
# DATABASE
# =====================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 0,
            username TEXT,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER DEFAULT 2,
            status TEXT DEFAULT 'waiting_payment',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    # Добавляем колонки если их нет
    for col, col_type in {
        "guest_name":     "TEXT DEFAULT ''",
        "guest_phone":    "TEXT DEFAULT ''",
        "guest_email":    "TEXT DEFAULT ''",
        "guests_count":   "INTEGER DEFAULT 2",
        "notes":          "TEXT DEFAULT ''",
        "passport":       "TEXT DEFAULT ''",
        "payment_method": "TEXT DEFAULT 'tbank'",
        "total_price":    "INTEGER DEFAULT 0",
        "nights":         "INTEGER DEFAULT 1",
        "source":         "TEXT DEFAULT 'website'",
        "confirmed_at":   "TEXT DEFAULT ''",
        "promo_code":     "TEXT DEFAULT ''",
        "discount_percent": "INTEGER DEFAULT 0",
    }.items():
        try:
            conn.execute("ALTER TABLE bookings ADD COLUMN " + col + " " + col_type)
            conn.commit()
        except Exception:
            pass
    return conn

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
# API — PROMO CODES
# =====================================================

@app.get("/api/promo-codes")
async def get_promo_codes():
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.post("/api/promo-codes")
async def set_promo_codes(p: PromoCodes):
    # Нормализуем коды в верхний регистр — чтобы ввод не зависел от регистра
    normalized = {
        code.strip().upper(): percent
        for code, percent in p.codes.items()
        if code.strip()
    }
    with open(PROMO_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False)
    return {"ok": True}

@app.post("/api/promo-codes/validate")
async def validate_promo_code(v: PromoValidate):
    codes = {}
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "r", encoding="utf-8") as f:
            codes = json.load(f)
    code_norm = v.code.strip().upper()
    if code_norm in codes:
        return {"valid": True, "code": code_norm, "percent": codes[code_norm]}
    return {"valid": False, "percent": 0}

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
    return ""

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
    return PlainTextResponse("")

@app.post("/api/contract-template")
async def set_contract_template(c: ContractTemplate):
    with open(CONTRACT_FILE, "w", encoding="utf-8") as f:
        f.write(c.text)
    return {"ok": True}

# =====================================================
# API — BOOKINGS
# =====================================================

@app.get("/api/bookings")
async def get_bookings(admin: Optional[str] = None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM bookings ORDER BY check_in DESC").fetchall()
    conn.close()
    bookings = [dict(r) for r in rows]

    if admin:
        return bookings

    # Для сайта — только занятые даты (подтверждённые + ожидающие оплаты)
    booked = []
    checkout_dates = []
    for b in bookings:
        if b.get("status") in ("confirmed", "waiting_payment"):
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
    conn = get_db()
    booking_ref = "ГП-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    # Промокод проверяем на сервере — не доверяем процентам от клиента
    promo_code_clean = ""
    discount_percent = 0
    if b.promo_code:
        promo_codes_db = {}
        if os.path.exists(PROMO_FILE):
            with open(PROMO_FILE, "r", encoding="utf-8") as f:
                promo_codes_db = json.load(f)
        code_norm = b.promo_code.strip().upper()
        if code_norm in promo_codes_db:
            promo_code_clean = code_norm
            discount_percent = promo_codes_db[code_norm]

    conn.execute("""
        INSERT INTO bookings (
            user_id, username, check_in, check_out, guests, status,
            guest_name, guest_phone, guest_email, guests_count,
            notes, passport, payment_method, total_price, nights, source,
            promo_code, discount_percent
        ) VALUES (0, ?, ?, ?, ?, 'waiting_payment', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'website', ?, ?)
    """, (
        booking_ref, b.check_in, b.check_out, b.guests_count,
        b.guest_name, b.guest_phone, b.guest_email, b.guests_count,
        b.notes, b.passport, b.payment_method, b.total_price, b.nights,
        promo_code_clean, discount_percent
    ))
    conn.commit()
    conn.close()

    prepay = round(b.total_price * 0.2)

    # Email гостю — бронь создана
    import threading
    if b.guest_email:
        threading.Thread(target=email_booking_created, args=(
            booking_ref, b.guest_name, b.guest_email,
            b.check_in, b.check_out, b.nights, b.total_price, prepay
        )).start()
        # Email админу
        threading.Thread(target=email_admin_new_booking, args=(
            booking_ref, b.guest_name, b.guest_phone, b.guest_email,
            b.check_in, b.check_out, b.nights, b.total_price,
            promo_code_clean, discount_percent
        )).start()

    promo_line = ""
    if promo_code_clean:
        promo_line = (
            "\u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434: " + promo_code_clean +
            " (\u2212" + str(discount_percent) + "%)\n"
        )

    # Telegram — опционально
    for admin_id in ADMIN_IDS:
        try:
            await asyncio.wait_for(
                bot.send_message(
                    admin_id,
                    "\u041d\u043e\u0432\u0430\u044f \u0431\u0440\u043e\u043d\u044c \u0441 \u0441\u0430\u0439\u0442\u0430\n"
                    "\u0411\u0440\u043e\u043d\u044c: " + booking_ref + "\n"
                    "\u0413\u043e\u0441\u0442\u044c: " + b.guest_name + "\n"
                    "\u0422\u0435\u043b: " + b.guest_phone + "\n"
                    "\u0414\u0430\u0442\u044b: " + b.check_in + " \u2192 " + b.check_out + "\n"
                    "\u0421\u0443\u043c\u043c\u0430: " + str(b.total_price) + " \u20bd\n"
                    + promo_line +
                    "\u0421\u0442\u0430\u0442\u0443\u0441: \u0436\u0434\u0451\u0442 \u043e\u043f\u043b\u0430\u0442\u044b"
                ), timeout=3.0
            )
        except Exception:
            pass

    return {"booking_id": booking_ref, "status": "waiting_payment"}

@app.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: str, u: BookingUpdate):
    conn = get_db()
    conn.execute("UPDATE bookings SET status=? WHERE id=?", (u.status, booking_id))
    conn.commit()
    conn.close()
    return {"ok": True}

# =====================================================
# API — ПОДТВЕРЖДЕНИЕ ОПЛАТЫ (из веб-админки)
# =====================================================

@app.post("/api/bookings/{booking_ref}/confirm")
async def confirm_booking(booking_ref: str):
    """Подтверждение оплаты из веб-админки — главный флоу."""
    conn = get_db()

    # Ищем по username (booking_ref) или id
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? OR CAST(id AS TEXT)=? LIMIT 1",
        (booking_ref, booking_ref)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = dict(row)

    # Меняем статус на confirmed
    conn.execute(
        "UPDATE bookings SET status='confirmed', confirmed_at=? WHERE id=?",
        (datetime.now().isoformat(), booking["id"])
    )
    conn.commit()
    conn.close()

    # Получаем код замка
    door_code_data = json.load(open(CODE_FILE)) if os.path.exists(CODE_FILE) else {}
    door_code = door_code_data.get("code") or load_door_code()

    # Обновляем данные брони
    booking["status"] = "confirmed"

    # Отправляем email с договором и кодом замка
    guest_email = booking.get("guest_email", "")
    if guest_email:
        import threading
        threading.Thread(
            target=email_booking_confirmed,
            args=(booking, door_code)
        ).start()

    # Telegram уведомление
    for admin_id in ADMIN_IDS:
        try:
            await asyncio.wait_for(
                bot.send_message(
                    admin_id,
                    "\u2705 \u0411\u0440\u043e\u043d\u044c \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430\n" +
                    str(booking.get("username", booking["id"]))
                ), timeout=3.0
            )
        except Exception:
            pass

    return {"ok": True, "booking_id": booking.get("username"), "door_code": door_code}

@app.post("/api/bookings/{booking_ref}/cancel")
async def cancel_booking_api(booking_ref: str):
    """Отмена брони из веб-админки."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? OR CAST(id AS TEXT)=? LIMIT 1",
        (booking_ref, booking_ref)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Booking not found")
    conn.execute(
        "UPDATE bookings SET status='cancelled' WHERE id=?",
        (row["id"],)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# =====================================================
# API — PAYMENT NOTIFY (гость нажал "Я оплатил")
# =====================================================

@app.post("/api/payment-notify")
async def payment_notify(p: PaymentNotify):
    """Гость сообщил об оплате — меняем статус на payment_pending."""
    conn = get_db()
    conn.execute(
        "UPDATE bookings SET status='payment_pending' WHERE username=?",
        (p.booking_ref,)
    )
    conn.commit()
    conn.close()

    prepay = round(p.total_price * 0.2)

    # Email админу
    import threading
    threading.Thread(target=send_email, args=(
        MAIL_ADMIN,
        "\u0413\u043e\u0441\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0438\u043b \u043e\u0431 \u043e\u043f\u043b\u0430\u0442\u0435 \u2014 " + p.booking_ref,
        "<div style='font-family:Arial;padding:24px;background:#0A0A0A;color:#F0E6C8'>"
        "<h2 style='color:#C9A84C'>\u0413\u043e\u0441\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0438\u043b \u043e\u0431 \u043e\u043f\u043b\u0430\u0442\u0435</h2>"
        "<p>\u0411\u0440\u043e\u043d\u044c: <b>" + p.booking_ref + "</b></p>"
        "<p>\u0413\u043e\u0441\u0442\u044c: " + p.guest_name + "</p>"
        "<p>\u0422\u0435\u043b: " + p.guest_phone + "</p>"
        "<p>\u0421\u0443\u043c\u043c\u0430: " + str(p.total_price) + " \u20bd</p>"
        "<p>\u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 20%: " + str(prepay) + " \u20bd</p>"
        "<p><a href='https://citypause.ru/static/admin.html' style='color:#C9A84C'>"
        "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435 \u0432 \u0430\u0434\u043c\u0438\u043d\u043a\u0435</a></p>"
        "</div>"
    )).start()

    # Telegram
    for admin_id in ADMIN_IDS:
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            await asyncio.wait_for(
                bot.send_message(
                    admin_id,
                    "\u0413\u043e\u0441\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0438\u043b \u043e\u0431 \u043e\u043f\u043b\u0430\u0442\u0435\n"
                    "\u0411\u0440\u043e\u043d\u044c: " + p.booking_ref + "\n"
                    "\u0413\u043e\u0441\u0442\u044c: " + p.guest_name
                ), timeout=3.0
            )
        except Exception as e:
            print("TG notify error: " + str(e))

    return {"ok": True}

# =====================================================
# API — CONTRACTS
# =====================================================

@app.get("/api/contracts/{booking_ref}")
async def get_contract(booking_ref: str):
    """Получить сохранённый договор."""
    path = os.path.join(CONTRACTS_DIR, booking_ref + ".txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    # Генерируем на лету
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? OR CAST(id AS TEXT)=? LIMIT 1",
        (booking_ref, booking_ref)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    return PlainTextResponse(generate_contract(dict(row)))

# =====================================================
# CALLBACKS (Telegram)
# =====================================================

from aiogram.types import CallbackQuery

@dp.callback_query(lambda c: c.data.startswith("web_confirm_"))
async def web_payment_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_confirm_", "")
    # Используем основной эндпоинт подтверждения
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE username=? LIMIT 1", (booking_ref,)).fetchone()
    conn.close()
    if row:
        booking = dict(row)
        booking["status"] = "confirmed"
        door_code_data = json.load(open(CODE_FILE)) if os.path.exists(CODE_FILE) else {}
        door_code = door_code_data.get("code") or load_door_code()
        conn2 = get_db()
        conn2.execute("UPDATE bookings SET status='confirmed' WHERE username=?", (booking_ref,))
        conn2.commit()
        conn2.close()
        import threading
        if booking.get("guest_email"):
            threading.Thread(target=email_booking_confirmed, args=(booking, door_code)).start()
    try:
        await callback.message.edit_text(callback.message.text + "\n\n\u2705 \u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e")
    except Exception:
        pass
    await callback.answer("\u2705")

@dp.callback_query(lambda c: c.data.startswith("web_reject_"))
async def web_payment_reject(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    booking_ref = callback.data.replace("web_reject_", "")
    conn = get_db()
    conn.execute("UPDATE bookings SET status='cancelled' WHERE username=?", (booking_ref,))
    conn.commit()
    conn.close()
    try:
        await callback.message.edit_text(callback.message.text + "\n\n\u274c \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")
    except Exception:
        pass
    await callback.answer("\u274c")

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
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u043e \u0432\u044b\u0435\u0437\u0434\u0435 \u2014 \u0441\u0435\u0433\u043e\u0434\u043d\u044f \u0434\u043e 12:00\n\n"
                                "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u0435\u0440\u0435\u0434 \u0443\u0445\u043e\u0434\u043e\u043c:\n"
                                "- \u041e\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u043a\u043b\u044e\u0447\u0438 \u0432 \u043f\u043e\u0447\u0442\u043e\u0432\u043e\u043c \u044f\u0449\u0438\u043a\u0435\n"
                                "- \u0417\u0430\u043a\u0440\u043e\u0439\u0442\u0435 \u043e\u043a\u043d\u0430 \u0438 \u0431\u0430\u043b\u043a\u043e\u043d\n"
                                "- \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u0435 \u0441\u0432\u0435\u0442 \u0438 \u0442\u0435\u0445\u043d\u0438\u043a\u0443\n"
                                "- \u0417\u0430\u0445\u043b\u043e\u043f\u043d\u0438\u0442\u0435 \u0434\u0432\u0435\u0440\u044c\n\n"
                                "\u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0447\u0442\u043e \u0432\u044b\u0431\u0440\u0430\u043b\u0438 \u043d\u0430\u0441! \ud83e\udd17"
                            ), timeout=5.0)
                        except Exception:
                            pass

            if hour == 12 and minute < 30:
                bookings  = get_bookings_checkin_tomorrow()
                door_code = load_door_code()
                for b in bookings:
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\ud83c\udfe0 \u0417\u0430\u0432\u0442\u0440\u0430 \u0432\u0430\u0448 \u0437\u0430\u0435\u0437\u0434!\n\n"
                                "\ud83d\udccd \u0443\u043b. \u0414\u0430\u0447\u043d\u0430\u044f, \u0434. 5, \u043a\u0432. 286\n"
                                "\ud83d\udd10 \u041a\u043e\u0434 \u0437\u0430\u043c\u043a\u0430: " + str(door_code) + "\n"
                                "\ud83d\udee7 \u041b\u0438\u0444\u0442: 22 \u044d\u0442\u0430\u0436\n"
                                "\ud83d\udcb0 \u0414\u0435\u043f\u043e\u0437\u0438\u0442 6 000 \u20bd \u043f\u0440\u0438 \u0437\u0430\u0441\u0435\u043b\u0435\u043d\u0438\u0438"
                            ), timeout=5.0)
                        except Exception:
                            pass

            if hour == 15 and minute < 30:
                bookings = get_bookings_checkin_today()
                for b in bookings:
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\ud83c\udf89 \u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c!\n\n"
                                "\u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0432\u0430\u0448 \u0437\u0430\u0435\u0437\u0434 \u0432 \u00ab\u0413\u043e\u0440\u043e\u0434\u0441\u043a\u0430\u044f \u041f\u0430\u0443\u0437\u0430\u00bb.\n"
                                "\u0417\u0430\u0435\u0437\u0434 \u0441 15:00 \u2014 \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u0430 \u0433\u043e\u0442\u043e\u0432\u0430. \ud83e\udd17"
                            ), timeout=5.0)
                        except Exception:
                            pass

            if hour == 14 and minute < 30:
                bookings = get_bookings_checkout_yesterday()
                for b in bookings:
                    if b.get("user_id") and b["user_id"] != 0:
                        try:
                            await asyncio.wait_for(bot.send_message(
                                b["user_id"],
                                "\ud83d\ude4f \u0421\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u0432\u0438\u0437\u0438\u0442!\n\n"
                                "\u0411\u0443\u0434\u0435\u043c \u0440\u0430\u0434\u044b \u0432\u0438\u0434\u0435\u0442\u044c \u0432\u0430\u0441 \u0441\u043d\u043e\u0432\u0430! \ud83c\udfe0\u2728"
                            ), timeout=5.0)
                        except Exception:
                            pass
        except Exception as e:
            print("Scheduler error: " + str(e))
        await asyncio.sleep(30 * 60)

# =====================================================
# STARTUP / SHUTDOWN
# =====================================================

@app.on_event("startup")
async def startup():
    print("APPLICATION STARTED")
    async def safe_polling():
        while True:
            try:
                await dp.start_polling(bot)
            except Exception as e:
                print("Bot polling error: " + str(e))
                await asyncio.sleep(30)
    asyncio.create_task(safe_polling())
    asyncio.create_task(send_notifications())
    print("SCHEDULER STARTED")

@app.on_event("shutdown")
async def shutdown():
    print("APPLICATION STOPPED")
    await bot.session.close()
