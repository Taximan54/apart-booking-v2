"""API: брони, блокировка дат, подтверждение и уведомления об оплате."""
import asyncio
import json
import os
import random
import secrets
import string
from datetime import datetime, timedelta
from fastapi import APIRouter, Header, Depends, HTTPException
from typing import Optional

from config import ADMIN_IDS, BASE_URL
from core.auth import require_admin, verify_token
from core.constants import PROMO_FILE, CODE_FILE, CONTRACTS_DIR, PASSPORT_DIR, MAIL_ADMIN
from core.contract_docs import save_contract, generate_contract
from core.data_store import get_default_deposit
from core.db import get_db
from core.mailer import send_email
from core.models import (
    BookingCreate,
    ManualBookingCreate,
    ResendContract,
    BlockDatesRequest,
    UnblockDatesRequest,
    BookingUpdate,
    PaymentNotify,
)
from core.passports import load_passport_map, save_passport_map
from core.runtime import bot, now_nsk
from core.signing import (
    email_booking_created,
    email_admin_new_booking,
    email_complete_data_request,
    email_contract_signed,
    email_booking_confirmed,
    email_checkin_memo,
)
from core.validators import _phone_digits_ok, _passport_digits_ok
from handlers.admin import load_door_code
from services.booking_service import db_lock, is_dates_available, DEFAULT_PROPERTY_ID
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =====================================================
# API — BOOKINGS
# =====================================================

@router.get("/api/bookings")
async def get_bookings(admin: Optional[str] = None, authorization: Optional[str] = Header(None)):
    if admin:
        if not authorization or not authorization.startswith("Bearer ") \
           or not verify_token(authorization[len("Bearer "):]):
            raise HTTPException(status_code=401, detail="Unauthorized")
    conn = get_db()
    rows = conn.execute("SELECT * FROM bookings ORDER BY check_in DESC").fetchall()
    conn.close()
    bookings = [dict(r) for r in rows]

    if admin:
        pm = load_passport_map()
        for bk in bookings:
            ref = bk.get("username") or str(bk.get("id", ""))
            entry = pm.get(ref)
            slots = []
            if isinstance(entry, dict):
                slots = [s for s in ("main", "reg1") if entry.get(s)]
            bk["has_passport_photo"] = bool(slots)
            bk["passport_photo_slots"] = slots
        return bookings

    # Для сайта — занятые даты. ВАЖНО: раньше здесь была отдельная,
    # отдельно захардкоженная проверка "status in ('confirmed', 'waiting_payment')",
    # рассинхронизированная с is_dates_available()/get_booked_ranges() — из-за
    # неё брони со статусами 'blocked', 'fully_paid', 'payment_pending' не
    # считались занятыми на сайте. Теперь логика одна и та же везде: занято
    # всё, что не отменено.
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

@router.post("/api/bookings")
async def create_booking(b: BookingCreate):
    # Проверка минимального срока бронирования
    try:
        d_in  = datetime.strptime(b.check_in,  "%Y-%m-%d").date()
        d_out = datetime.strptime(b.check_out, "%Y-%m-%d").date()
        nights_count = (d_out - d_in).days
    except Exception:
        raise HTTPException(status_code=400, detail="\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0434\u0430\u0442")
    if nights_count < 2:
        raise HTTPException(status_code=400, detail="\u041c\u0438\u043d\u0438\u043c\u0430\u043b\u044c\u043d\u044b\u0439 \u0441\u0440\u043e\u043a \u0431\u0440\u043e\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f \u2014 2 \u043d\u043e\u0447\u0438")
    if not _phone_digits_ok(b.guest_phone):
        raise HTTPException(status_code=400, detail="Некорректный номер телефона — должно быть 10 цифр после +7")
    if not _passport_digits_ok(b.passport):
        raise HTTPException(status_code=400, detail="Некорректные паспортные данные — серия (4 цифры) и номер (6 цифр)")

    # Защита от двойного бронирования: проверка занятости дат под глобальной
    # блокировкой, чтобы два гостя не забронировали одни и те же даты одновременно
    with db_lock:
        if not is_dates_available(b.check_in, b.check_out, property_id=DEFAULT_PROPERTY_ID):
            raise HTTPException(status_code=409, detail="К сожалению, эти даты только что забронировали. Пожалуйста, выберите другие даты.")

        conn = get_db()
        booking_ref = "GP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, guest_phone, guest_email, guests_count,
                notes, passport, payment_method, total_price, nights, source,
                promo_code, discount_percent
            ) VALUES (?, 0, ?, ?, ?, ?, 'waiting_payment', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'website', ?, ?)
        """, (
            DEFAULT_PROPERTY_ID,
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
        except Exception as e:
            logger.warning("Telegram: не отправлено уведомление о новой брони: %s", e)

    if b.passport_photo_main or b.passport_photo_reg1:
        pm = load_passport_map()
        pm[booking_ref] = {
            "main": b.passport_photo_main,
            "reg1": b.passport_photo_reg1,
        }
        save_passport_map(pm)

    return {"booking_id": booking_ref, "status": "waiting_payment"}

@router.post("/api/admin/manual-booking")
async def create_manual_booking(b: ManualBookingCreate, _: bool = Depends(require_admin)):
    """
    Ручное создание брони для внешних площадок (Авито, Яндекс.Путешествия,
    Суточно.ру и т.д.), которые оформлены не через сайт. Бронь сразу
    подтверждена и блокирует даты в календаре. Если email указан —
    гостю на почту уходит ссылка на страницу, где он донабирает недостающее
    (паспортные данные, если админ их не указал, и обязательно — фото
    паспорта) и подписывает договор. Если email не указан (площадки типа
    Авито часто не дают контакты гостя) — ссылка возвращается в ответе,
    чтобы админ скопировал её и отправил гостю вручную через чат площадки.
    """
    try:
        d_in  = datetime.strptime(b.check_in,  "%Y-%m-%d").date()
        d_out = datetime.strptime(b.check_out, "%Y-%m-%d").date()
        nights_count = (d_out - d_in).days
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный формат дат")
    if nights_count < 1:
        raise HTTPException(status_code=400, detail="Дата выезда должна быть позже даты заезда")

    valid_sources = {"avito", "yandex", "sutochno", "phone", "other"}
    source = b.source if b.source in valid_sources else "other"
    deposit = b.deposit or get_default_deposit()
    sign_token = secrets.token_urlsafe(24)

    with db_lock:
        if not is_dates_available(b.check_in, b.check_out, property_id=DEFAULT_PROPERTY_ID):
            raise HTTPException(status_code=409, detail="Эти даты уже заняты другой бронью — проверьте календарь")

        conn = get_db()
        booking_ref = "GP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        conn.execute("""
            INSERT INTO bookings (
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, guest_phone, guest_email, guests_count,
                notes, passport, payment_method, total_price, nights, source,
                promo_code, discount_percent, deposit, sign_token
            ) VALUES (?, 0, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?, ?, ?, 'external', ?, ?, ?, '', 0, ?, ?)
        """, (
            DEFAULT_PROPERTY_ID,
            booking_ref, b.check_in, b.check_out, b.guests_count,
            b.guest_name, b.guest_phone, b.guest_email, b.guests_count,
            b.notes, b.passport, b.total_price, nights_count, source,
            deposit, sign_token
        ))
        conn.commit()
        conn.close()

    booking_dict = {
        "username": booking_ref,
        "guest_name": b.guest_name,
        "guest_email": b.guest_email,
        "guest_phone": b.guest_phone,
        "passport": b.passport,
        "check_in": b.check_in,
        "check_out": b.check_out,
        "nights": nights_count,
        "guests_count": b.guests_count,
        "total_price": b.total_price,
        "deposit": deposit,
        "discount_percent": 0,
        "sign_token": sign_token,
    }

    # Сохраняем черновик текста договора в архив (для админки — там уже будет
    # актуальный текст, даже до того как гость донаполнит паспортные данные)
    save_contract(booking_ref, generate_contract(booking_dict))

    sign_link = f"{BASE_URL}/complete/{sign_token}"
    if b.guest_email.strip():
        import threading
        threading.Thread(target=email_complete_data_request, args=(booking_dict,)).start()

    return {"ok": True, "booking_ref": booking_ref, "sign_link": sign_link, "email_sent": bool(b.guest_email.strip())}

@router.get("/api/admin/bookings/{ref}/sign-link")
async def get_sign_link(ref: str, _: bool = Depends(require_admin)):
    """Возвращает ссылку на страницу заполнения/подписания для брони — чтобы скопировать и отправить гостю вручную (например, в чат Авито)."""
    conn = get_db()
    row = conn.execute("SELECT sign_token, signed_at FROM bookings WHERE username = ?", (ref,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    booking = dict(row)
    if not booking.get("sign_token"):
        # На случай очень старых броней без токена
        conn = get_db()
        sign_token = secrets.token_urlsafe(24)
        conn.execute("UPDATE bookings SET sign_token=? WHERE username=?", (sign_token, ref))
        conn.commit()
        conn.close()
        booking["sign_token"] = sign_token
    return {
        "sign_link": f"{BASE_URL}/complete/{booking['sign_token']}",
        "already_signed": bool(booking.get("signed_at")),
    }

@router.post("/api/admin/bookings/{ref}/resend-contract")
async def resend_contract(ref: str, r: ResendContract, _: bool = Depends(require_admin)):
    """
    Повторная отправка на указанный email:
    — если договор уже подписан гостем — уходят готовые подписанные PDF
      (договор + согласие на ПД), как обычно;
    — если ещё не подписан — повторно уходит ссылка на заполнение данных
      и подписание (на новый email, если гость его сменил).
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE username = ?", (ref,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    booking = dict(row)

    if booking.get("signed_at"):
        booking["guest_email"] = r.email or booking.get("guest_email", "")
        email_contract_signed(booking)
    else:
        if not booking.get("sign_token"):
            # На случай очень старых броней без токена (созданных до этой функции)
            conn = get_db()
            sign_token = secrets.token_urlsafe(24)
            conn.execute("UPDATE bookings SET sign_token=? WHERE id=?", (sign_token, booking["id"]))
            conn.commit()
            conn.close()
            booking["sign_token"] = sign_token
        booking["guest_email"] = r.email or booking.get("guest_email", "")
        email_complete_data_request(booking)
    return {"ok": True}

# =====================================================
# API — БЛОКИРОВКА ДАТ АДМИНИСТРАТОРОМ
# =====================================================
# ВАЖНО: раньше это хранилось только в localStorage браузера админки и
# ничего не писало в БД (эндпоинтов /api/blocked-dates и /api/unblock-dates
# не существовало — ошибка вызова гасилась пустым catch(e){}). Из-за этого
# "заблокированные" даты не учитывались ни на сайте, ни при проверке
# занятости, и гости могли забронировать их напрямую. Теперь блокировка —
# настоящая запись в bookings со статусом 'blocked', которая проходит через
# ту же защиту db_lock + is_dates_available, что и обычные брони.

@router.post("/api/blocked-dates")
async def create_blocked_dates(b: BlockDatesRequest, _: bool = Depends(require_admin)):
    if not b.dates:
        raise HTTPException(status_code=400, detail="Не выбраны даты")
    dates_sorted = sorted(b.dates)
    check_in = dates_sorted[0]
    check_out = (datetime.strptime(dates_sorted[-1], "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
    nights = (datetime.strptime(check_out, "%Y-%m-%d").date() - datetime.strptime(check_in, "%Y-%m-%d").date()).days

    with db_lock:
        if not is_dates_available(check_in, check_out, property_id=DEFAULT_PROPERTY_ID):
            raise HTTPException(status_code=409, detail="На эти даты уже есть бронь или блокировка")

        conn = get_db()
        booking_ref = "BLOCK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        conn.execute("""
            INSERT INTO bookings (
                property_id, user_id, username, check_in, check_out, guests, status,
                guest_name, notes, total_price, nights, source
            ) VALUES (?, 0, ?, ?, ?, 0, 'blocked', 'Заблокировано администратором', ?, 0, ?, 'admin_block')
        """, (
            DEFAULT_PROPERTY_ID, booking_ref, check_in, check_out, b.reason, nights
        ))
        conn.commit()
        conn.close()

    return {"ok": True, "blocked_days": len(dates_sorted)}

@router.post("/api/unblock-dates")
async def remove_blocked_dates(u: UnblockDatesRequest, _: bool = Depends(require_admin)):
    """Отменяет (status='cancelled') записи-блокировки ('blocked'), пересекающиеся с диапазоном."""
    end_exclusive = (datetime.strptime(u.end, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")

    conn = get_db()
    rows = conn.execute("""
        SELECT id FROM bookings
        WHERE property_id = ? AND status = 'blocked'
        AND check_in < ? AND check_out > ?
    """, (DEFAULT_PROPERTY_ID, end_exclusive, u.start)).fetchall()
    ids = [row["id"] for row in rows]
    if ids:
        conn.executemany("UPDATE bookings SET status='cancelled' WHERE id=?", [(i,) for i in ids])
        conn.commit()
    conn.close()

    return {"ok": True, "unblocked": len(ids)}

@router.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: str, u: BookingUpdate, _: bool = Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE bookings SET status=? WHERE id=?", (u.status, booking_id))
    conn.commit()
    conn.close()
    return {"ok": True}

# =====================================================
# API — ПОДТВЕРЖДЕНИЕ ОПЛАТЫ (из веб-админки)
# =====================================================

@router.post("/api/bookings/{booking_ref}/confirm")
async def confirm_booking(booking_ref: str, _: bool = Depends(require_admin)):
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

    # Токен для ссылки на страницу SMS-подписания
    sign_token = secrets.token_urlsafe(24)

    # Меняем статус на confirmed
    conn.execute(
        "UPDATE bookings SET status='confirmed', confirmed_at=?, sign_token=? WHERE id=?",
        (datetime.now().isoformat(), sign_token, booking["id"])
    )
    conn.commit()
    conn.close()

    # Получаем код замка
    door_code_data = json.load(open(CODE_FILE)) if os.path.exists(CODE_FILE) else {}
    door_code = door_code_data.get("code") or load_door_code()

    # Обновляем данные брони
    booking["status"] = "confirmed"
    booking["sign_token"] = sign_token

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
        except Exception as e:
            logger.warning("Telegram: не отправлено уведомление о подтверждении брони: %s", e)

    return {"ok": True, "booking_id": booking.get("username"), "door_code": door_code}

@router.post("/api/bookings/{booking_ref}/full-payment")
async def full_payment(booking_ref: str, _: bool = Depends(require_admin)):
    """Подтверждение полной оплаты — отправляет гостю памятку с кодом замка."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE id=? OR username=?",
        (booking_ref, booking_ref)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="\u0411\u0440\u043e\u043d\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430")
    booking = dict(row)
    now_str = now_nsk().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "UPDATE bookings SET status='fully_paid', fully_paid_at=? WHERE id=? OR username=?",
        (now_str, booking_ref, booking_ref)
    )
    conn.commit()
    conn.close()

    door_code = load_door_code()
    guest_email = booking.get("guest_email", "")
    guest_name  = booking.get("guest_name", "")
    check_in    = booking.get("check_in", "")

    import threading
    if guest_email:
        threading.Thread(target=email_checkin_memo, args=(
            guest_name, guest_email, booking_ref, check_in, door_code
        )).start()

    for admin_id in ADMIN_IDS:
        try:
            import asyncio as _asyncio
            await _asyncio.wait_for(
                bot.send_message(admin_id,
                    "\u2705 \u041f\u043e\u043b\u043d\u0430\u044f \u043e\u043f\u043b\u0430\u0442\u0430 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0430\n"
                    "\u0411\u0440\u043e\u043d\u044c: " + booking_ref + "\n"
                    "\u0413\u043e\u0441\u0442\u044c: " + guest_name + "\n"
                    "\u041f\u0430\u043c\u044f\u0442\u043a\u0430 \u0441 \u043a\u043e\u0434\u043e\u043c \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0430 \u0433\u043e\u0441\u0442\u044e"
                ), timeout=3.0
            )
        except Exception as e:
            logger.warning("Telegram: не отправлена памятка с кодом замка: %s", e)

    return {"ok": True, "status": "fully_paid"}

@router.post("/api/bookings/{booking_ref}/cancel")
async def cancel_booking_api(booking_ref: str, _: bool = Depends(require_admin)):
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

def _delete_contract_files_and_photos(ref):
    """
    Удаляет с диска всё, что относится к договору брони ref: черновик
    (.txt), подписанные PDF (договор + согласие на ПД), фото паспорта и
    запись о них в PASSPORT_MAP_FILE. НЕ трогает саму запись брони в БД —
    это отдельная операция (см. delete_booking_api). Работает и для
    "осиротевших" файлов, у которых брони в БД уже нет.
    """
    for candidate in {ref, ref.replace("GP-", "\u0413\u041f-")}:
        for suffix in (".txt", "_podpisan.pdf", "_soglasie_pd.pdf"):
            path = os.path.join(CONTRACTS_DIR, candidate + suffix)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Не удалось удалить файл договора {path}: {e}")

    pm = load_passport_map()
    for candidate in {ref, ref.replace("GP-", "\u0413\u041f-")}:
        entry = pm.get(candidate)
        if isinstance(entry, dict):
            for slot_file in entry.values():
                if not slot_file:
                    continue
                fpath = os.path.join(PASSPORT_DIR, slot_file)
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        logger.warning(f"Не удалось удалить фото паспорта {fpath}: {e}")
            pm.pop(candidate, None)
    save_passport_map(pm)

@router.delete("/api/bookings/{booking_ref}")
async def delete_booking_api(booking_ref: str, _: bool = Depends(require_admin)):
    """
    Полностью и безвозвратно удаляет бронь: саму запись в БД и все файлы
    договора (см. _delete_contract_files_and_photos). Используется в
    основном для очистки тестовых броней. Подтверждение запрашивается на
    клиенте перед вызовом — это необратимое действие.
    """
    ref_alt = booking_ref.replace("GP-", "\u0413\u041f-")
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bookings WHERE username=? OR username=? OR CAST(id AS TEXT)=? LIMIT 1",
        (booking_ref, ref_alt, booking_ref)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Booking not found")
    ref = row["username"] or str(row["id"])
    conn.execute("DELETE FROM bookings WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()

    _delete_contract_files_and_photos(ref)
    return {"ok": True}

@router.delete("/api/contracts/{ref}")
async def delete_contract_archive_entry(ref: str, _: bool = Depends(require_admin)):
    """
    Удаляет договор из архива вручную: черновик, подписанные PDF и фото
    паспорта — независимо от того, существует ли ещё сама бронь в БД
    (например, если бронь уже была удалена раньше, а файлы остались, или
    наоборот — нужно почистить только документы тестовой брони). Если
    подходящая бронь в БД найдена — удаляется и она тоже, для полной
    очистки. Подтверждение запрашивается на клиенте — действие необратимо.
    """
    _delete_contract_files_and_photos(ref)

    ref_alt = ref.replace("GP-", "\u0413\u041f-")
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM bookings WHERE username=? OR username=? OR CAST(id AS TEXT)=? LIMIT 1",
        (ref, ref_alt, ref)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM bookings WHERE id=?", (row["id"],))
        conn.commit()
    conn.close()
    return {"ok": True}

# =====================================================
# API — PAYMENT NOTIFY (гость нажал "Я оплатил")
# =====================================================

@router.post("/api/payment-notify")
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
            logger.error("TG notify error: " + str(e), exc_info=True)

    return {"ok": True}
