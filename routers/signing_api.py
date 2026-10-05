"""API: подписание договора гостем и донаполнение данных ручной брони."""
import os
from fastapi import APIRouter, Request, UploadFile, Form, File, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.contract_docs import contract_text_to_html, generate_contract, generate_consent
from core.db import get_db
from core.passports import load_passport_map, save_uploaded_passport_photo, set_passport_slot
from core.runtime import now_nsk
from core.signing import email_contract_signed
from core.validators import _phone_digits_ok, _passport_digits_ok
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =====================================================
# API — ПОДПИСАНИЕ ДОГОВОРА (ПЭП, публичные эндпоинты по токену)
# =====================================================
# Подписание — по персональной ссылке из письма (без SMS-кода): переход
# по уникальной ссылке и нажатие кнопки «Подписать» на этой странице и
# есть простая электронная подпись (ссылка известна только гостю, т.к.
# отправлена на его собственный email).

@router.get("/sign/{token}", response_class=HTMLResponse)
async def sign_page(token: str):
    """Публичная страница подписания — статика, токен разбирается на клиенте из URL."""
    path = os.path.join("static", "sign.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)

@router.get("/api/sign/{token}")
async def get_sign_info(token: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE sign_token=?", (token,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    booking = dict(row)
    if booking.get("signed_at"):
        return {"already_signed": True, "signed_at": booking["signed_at"]}

    booking_ref = str(booking.get("username") or booking.get("id", ""))
    pm = load_passport_map()
    entry = pm.get(booking_ref, {}) if isinstance(pm.get(booking_ref), dict) else {}
    return {
        "already_signed": False,
        "booking_ref": booking_ref,
        "guest_name": booking.get("guest_name"),
        "guest_phone": booking.get("guest_phone"),
        "guest_email": booking.get("guest_email"),
        "passport": booking.get("passport"),
        "photos_uploaded": {"main": bool(entry.get("main")), "reg1": bool(entry.get("reg1"))},
        "contract_html": contract_text_to_html(generate_contract(booking)),
        "consent_html":  contract_text_to_html(generate_consent(booking), flat_numbering=True),
    }

@router.post("/api/sign/{token}/confirm")
async def confirm_sign(token: str, request: Request):
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE sign_token=?", (token,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    booking = dict(row)
    if booking.get("signed_at"):
        conn.close()
        raise HTTPException(status_code=400, detail="Договор уже подписан")

    signed_at = now_nsk().strftime("%Y-%m-%d %H:%M:%S")
    client_ip = request.client.host if request.client else ""
    conn.execute("UPDATE bookings SET signed_at=?, sign_ip=? WHERE id=?", (signed_at, client_ip, booking["id"]))
    conn.commit()
    conn.close()

    booking["signed_at"] = signed_at
    booking["sign_ip"] = client_ip
    import threading
    threading.Thread(target=email_contract_signed, args=(booking,)).start()

    return {"ok": True, "signed_at": signed_at}



# =====================================================
# API — ДОЗАПОЛНЕНИЕ ДАННЫХ И ПОДПИСАНИЕ РУЧНОЙ БРОНИ
# =====================================================
# Используется, когда бронь создана администратором вручную (Авито и т.п.):
# гость по ссылке донабирает недостающее (паспорт, если админ не указал его
# сам — вариант "гость заполняет всё сам"; если указал — просит только фото)
# и подписывает, точно так же как и на сайте.

class CompleteSubmit(BaseModel):
    passport: str = ""
    guest_name: str = ""
    guest_phone: str = ""
    guest_email: str = ""

@router.get("/complete/{token}", response_class=HTMLResponse)
async def complete_page(token: str):
    path = os.path.join("static", "complete.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)

@router.get("/api/complete/{token}")
async def get_complete_info(token: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE sign_token=?", (token,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    booking = dict(row)
    if booking.get("signed_at"):
        return {"already_signed": True, "signed_at": booking["signed_at"]}

    booking_ref = str(booking.get("username") or booking.get("id", ""))
    pm = load_passport_map()
    entry = pm.get(booking_ref, {}) if isinstance(pm.get(booking_ref), dict) else {}
    return {
        "already_signed": False,
        "booking_ref": booking_ref,
        "guest_name": booking.get("guest_name"),
        "name_needed": not bool((booking.get("guest_name") or "").strip()),
        "phone_needed": not bool((booking.get("guest_phone") or "").strip()),
        "email_needed": not bool((booking.get("guest_email") or "").strip()),
        "passport_needed": not bool((booking.get("passport") or "").strip()),
        "photos_uploaded": {"main": bool(entry.get("main")), "reg1": bool(entry.get("reg1"))},
        "contract_html": contract_text_to_html(generate_contract(booking)),
        "consent_html":  contract_text_to_html(generate_consent(booking), flat_numbering=True),
    }

@router.post("/api/complete/{token}/upload-photo")
async def upload_complete_photo(token: str, slot: str = Form(...), file: UploadFile = File(...)):
    if slot not in ("main", "reg1"):
        raise HTTPException(status_code=400, detail="Некорректный слот фото")
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE sign_token=?", (token,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    booking = dict(row)
    if booking.get("signed_at"):
        raise HTTPException(status_code=400, detail="Договор уже подписан")

    filename, _size = await save_uploaded_passport_photo(file)
    booking_ref = str(booking.get("username") or booking.get("id", ""))
    set_passport_slot(booking_ref, slot, filename)

    return {"ok": True}

@router.post("/api/complete/{token}/submit")
async def submit_complete(token: str, body: CompleteSubmit, request: Request):
    conn = get_db()
    row = conn.execute("SELECT * FROM bookings WHERE sign_token=?", (token,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    booking = dict(row)
    if booking.get("signed_at"):
        conn.close()
        raise HTTPException(status_code=400, detail="Договор уже подписан")

    booking_ref = str(booking.get("username") or booking.get("id", ""))
    name_needed = not bool((booking.get("guest_name") or "").strip())
    phone_needed = not bool((booking.get("guest_phone") or "").strip())
    email_needed = not bool((booking.get("guest_email") or "").strip())
    passport_needed = not bool((booking.get("passport") or "").strip())

    if name_needed and not body.guest_name.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Укажите ФИО")
    if phone_needed and not _phone_digits_ok(body.guest_phone):
        conn.close()
        raise HTTPException(status_code=400, detail="Укажите телефон полностью — 10 цифр после +7")
    if email_needed and "@" not in body.guest_email.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Укажите корректный email")
    if passport_needed and not _passport_digits_ok(body.passport):
        conn.close()
        raise HTTPException(status_code=400, detail="Укажите паспортные данные полностью — серия (4 цифры) и номер (6 цифр)")

    pm = load_passport_map()
    entry = pm.get(booking_ref, {}) if isinstance(pm.get(booking_ref), dict) else {}
    if not entry.get("main") or not entry.get("reg1"):
        conn.close()
        raise HTTPException(status_code=400, detail="Прикрепите оба фото паспорта")

    if name_needed:
        conn.execute("UPDATE bookings SET guest_name=? WHERE id=?", (body.guest_name.strip(), booking["id"]))
        booking["guest_name"] = body.guest_name.strip()
    if phone_needed:
        conn.execute("UPDATE bookings SET guest_phone=? WHERE id=?", (body.guest_phone.strip(), booking["id"]))
        booking["guest_phone"] = body.guest_phone.strip()
    if email_needed:
        conn.execute("UPDATE bookings SET guest_email=? WHERE id=?", (body.guest_email.strip(), booking["id"]))
        booking["guest_email"] = body.guest_email.strip()
    if passport_needed:
        conn.execute("UPDATE bookings SET passport=? WHERE id=?", (body.passport.strip(), booking["id"]))
        booking["passport"] = body.passport.strip()

    signed_at = now_nsk().strftime("%Y-%m-%d %H:%M:%S")
    client_ip = request.client.host if request.client else ""
    conn.execute("UPDATE bookings SET signed_at=?, sign_ip=? WHERE id=?", (signed_at, client_ip, booking["id"]))
    conn.commit()
    conn.close()

    booking["signed_at"] = signed_at
    booking["sign_ip"] = client_ip
    import threading
    threading.Thread(target=email_contract_signed, args=(booking,)).start()

    return {"ok": True, "signed_at": signed_at}
