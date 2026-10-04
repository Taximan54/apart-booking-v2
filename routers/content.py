"""API: отзывы, правила, настройки сайта, места, акции, контакты, оплата, код замка, описание."""
import asyncio
import io
import json
import os
import secrets
from PIL import Image
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from core.auth import require_admin
from core.backup import create_backup_zip, send_backup_everywhere
from core.constants import (
    REVIEWS_FILE,
    HOUSE_RULES_FILE,
    SETTINGS_FILE,
    PLACES_FILE,
    DISCOUNTS_FILE,
    CONTACTS_FILE,
    DEFAULT_CONTACTS,
    DEFAULT_PAYMENT_SETTINGS,
    PAYMENT_FILE,
    PAYMENT_QR_PATH,
    DATA_DIR,
    CODE_FILE,
    DESC_FILE,
)
from core.data_store import get_site_settings_dict, load_places, load_discounts
from core.db import get_db
from core.models import (
    Review,
    HouseRulesText,
    SiteSettings,
    Place,
    Discount,
    Contacts,
    PaymentSettings,
    DoorCode,
    Description,
)
from core.runtime import now_nsk
from handlers.admin import load_door_code

router = APIRouter()


# =====================================================
# API — REVIEWS
# =====================================================

@router.get("/api/reviews")
async def get_reviews():
    """Публичный эндпоинт — возвращает только видимые отзывы."""
    if os.path.exists(REVIEWS_FILE):
        with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            reviews = data if isinstance(data, list) else [data]
        return [r for r in reviews if r.get("visible", True)]
    return []

@router.get("/api/reviews/all")
async def get_all_reviews(_: bool = Depends(require_admin)):
    """Админский эндпоинт — возвращает все отзывы включая скрытые."""
    if os.path.exists(REVIEWS_FILE):
        with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else [data]
    return []

@router.post("/api/reviews")
async def add_review(r: Review, _: bool = Depends(require_admin)):
    """Добавить отзыв."""
    reviews = []
    if os.path.exists(REVIEWS_FILE):
        with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            reviews = data if isinstance(data, list) else [data]
    new_id = secrets.token_hex(6)
    review_dict = r.dict()
    review_dict["id"] = new_id
    reviews.append(review_dict)
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    return {"ok": True, "id": new_id}

@router.put("/api/reviews/{review_id}")
async def update_review(review_id: str, r: Review, _: bool = Depends(require_admin)):
    """Обновить или скрыть/показать отзыв."""
    if not os.path.exists(REVIEWS_FILE):
        raise HTTPException(status_code=404, detail="Нет отзывов")
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        reviews = data if isinstance(data, list) else [data]
    for i, rv in enumerate(reviews):
        if rv.get("id") == review_id:
            reviews[i] = {**r.dict(), "id": review_id}
            break
    else:
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    return {"ok": True}

@router.delete("/api/reviews/{review_id}")
async def delete_review(review_id: str, _: bool = Depends(require_admin)):
    """Удалить отзыв."""
    if not os.path.exists(REVIEWS_FILE):
        raise HTTPException(status_code=404, detail="Нет отзывов")
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        reviews = data if isinstance(data, list) else [data]
    reviews = [r for r in reviews if r.get("id") != review_id]
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    return {"ok": True}

# =====================================================
# API — HOUSE RULES
# =====================================================

DEFAULT_HOUSE_RULES = """ПРАВИЛА ПРОЖИВАНИЯ

1. Заезд с 15:00, выезд до 12:00.
2. Максимум 2 гостя.
3. Запрещено курение в квартире, на лоджии и в подъезде.
4. Запрещено проживание с животными.
5. Запрещено проведение шумных мероприятий.
6. Запрещено зажигать ароматические свечи.
7. Запрещено двигать мебель.
8. При выезде квартира сдаётся в чистом виде."""

@router.get("/api/house-rules")
async def get_house_rules():
    if os.path.exists(HOUSE_RULES_FILE):
        with open(HOUSE_RULES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return DEFAULT_HOUSE_RULES

@router.post("/api/house-rules")
async def set_house_rules(r: HouseRulesText, _: bool = Depends(require_admin)):
    with open(HOUSE_RULES_FILE, "w", encoding="utf-8") as f:
        f.write(r.text)
    return {"ok": True}

@router.get("/api/site-settings")
async def get_site_settings():
    return get_site_settings_dict()

@router.post("/api/site-settings")
async def set_site_settings(s: SiteSettings, _: bool = Depends(require_admin)):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s.dict(), f, ensure_ascii=False)
    return {"ok": True}

@router.post("/api/admin/bookings/{ref}/deposit-returned")
async def mark_deposit_returned(ref: str, _: bool = Depends(require_admin)):
    """Отмечает депозит по брони как возвращённый гостю (используется для дашборд-алертов)."""
    conn = get_db()
    row = conn.execute("SELECT id FROM bookings WHERE username = ?", (ref,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    conn.execute(
        "UPDATE bookings SET deposit_returned=1, deposit_returned_at=? WHERE username=?",
        (now_nsk().strftime("%Y-%m-%d %H:%M:%S"), ref)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@router.post("/api/admin/backup-now")
async def backup_now(_: bool = Depends(require_admin)):
    """
    Ручной запуск резервного копирования. Сам zip создаётся сразу (быстро,
    локально), а отправка в Telegram и на почту запускается фоновой задачей —
    иначе запрос из браузера успевает упасть по таймауту, пока идёт SMTP.
    """
    try:
        zip_path = create_backup_zip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка создания резервной копии: {e}")

    asyncio.create_task(send_backup_everywhere(zip_path))
    return {"ok": True, "started": True, "filename": os.path.basename(zip_path)}

def save_places(places):
    with open(PLACES_FILE, "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False, indent=2)

@router.get("/api/places")
async def get_places():
    """Публичный — только видимые места."""
    return [p for p in load_places() if p.get("visible", True)]

@router.get("/api/places/all")
async def get_all_places(_: bool = Depends(require_admin)):
    return load_places()

@router.post("/api/places")
async def add_place(p: Place, _: bool = Depends(require_admin)):
    places = load_places()
    if len(places) >= 10:
        raise HTTPException(status_code=400, detail="Максимум 10 мест")
    d = p.dict()
    d["id"] = secrets.token_hex(6)
    places.append(d)
    save_places(places)
    return {"ok": True, "id": d["id"]}

@router.put("/api/places/{place_id}")
async def update_place(place_id: str, p: Place, _: bool = Depends(require_admin)):
    places = load_places()
    for i, pl in enumerate(places):
        if pl.get("id") == place_id:
            places[i] = {**p.dict(), "id": place_id}
            save_places(places)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Место не найдено")

@router.delete("/api/places/{place_id}")
async def delete_place(place_id: str, _: bool = Depends(require_admin)):
    places = load_places()
    places = [p for p in places if p.get("id") != place_id]
    save_places(places)
    return {"ok": True}

def save_discounts(discounts):
    with open(DISCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(discounts, f, ensure_ascii=False, indent=2)

@router.get("/api/discounts")
async def get_discounts():
    """Публичный — только видимые акции/скидки."""
    return [d for d in load_discounts() if d.get("visible", True)]

@router.get("/api/discounts/all")
async def get_all_discounts(_: bool = Depends(require_admin)):
    return load_discounts()

@router.post("/api/discounts")
async def add_discount(d: Discount, _: bool = Depends(require_admin)):
    discounts = load_discounts()
    if len(discounts) >= 10:
        raise HTTPException(status_code=400, detail="Максимум 10 акций")
    row = d.dict()
    row["id"] = secrets.token_hex(6)
    discounts.append(row)
    save_discounts(discounts)
    return {"ok": True, "id": row["id"]}

@router.put("/api/discounts/{discount_id}")
async def update_discount(discount_id: str, d: Discount, _: bool = Depends(require_admin)):
    discounts = load_discounts()
    for i, row in enumerate(discounts):
        if row.get("id") == discount_id:
            discounts[i] = {**d.dict(), "id": discount_id}
            save_discounts(discounts)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Акция не найдена")

@router.delete("/api/discounts/{discount_id}")
async def delete_discount(discount_id: str, _: bool = Depends(require_admin)):
    discounts = load_discounts()
    discounts = [d for d in discounts if d.get("id") != discount_id]
    save_discounts(discounts)
    return {"ok": True}

@router.get("/api/contacts")
async def get_contacts():
    """Публичный — возвращает контактные данные."""
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_CONTACTS, **saved}
    return DEFAULT_CONTACTS

@router.post("/api/contacts")
async def set_contacts(c: Contacts, _: bool = Depends(require_admin)):
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(c.dict(), f, ensure_ascii=False)
    return {"ok": True}

# =====================================================
# API — ОПЛАТА (СБП: ссылка, телефон, свой QR-код)
# =====================================================

@router.get("/api/payment-settings")
async def get_payment_settings():
    """Публичный — ссылка/телефон для оплаты по СБП + есть ли загруженный QR-код."""
    settings = DEFAULT_PAYMENT_SETTINGS
    if os.path.exists(PAYMENT_FILE):
        with open(PAYMENT_FILE, "r", encoding="utf-8") as f:
            settings = {**DEFAULT_PAYMENT_SETTINGS, **json.load(f)}
    settings = dict(settings)
    settings["qr_uploaded"] = os.path.exists(PAYMENT_QR_PATH)
    return settings

@router.post("/api/payment-settings")
async def set_payment_settings(p: PaymentSettings, _: bool = Depends(require_admin)):
    with open(PAYMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(p.dict(), f, ensure_ascii=False)
    return {"ok": True}

@router.post("/api/payment-qr")
async def upload_payment_qr(file: UploadFile = File(...), _: bool = Depends(require_admin)):
    """Загрузка своего QR-кода для оплаты (картинка из банковского приложения)."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 10МБ)")
    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        os.makedirs(DATA_DIR, exist_ok=True)
        img.save(PAYMENT_QR_PATH, format="JPEG", quality=92)
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось обработать изображение")
    return {"ok": True}

@router.delete("/api/payment-qr")
async def delete_payment_qr(_: bool = Depends(require_admin)):
    if os.path.exists(PAYMENT_QR_PATH):
        os.remove(PAYMENT_QR_PATH)
    return {"ok": True}

@router.get("/api/payment-qr")
async def get_payment_qr():
    """Публичный — отдаёт загруженный QR-код оплаты как изображение."""
    if not os.path.exists(PAYMENT_QR_PATH):
        raise HTTPException(status_code=404, detail="QR-код не загружен")
    return FileResponse(PAYMENT_QR_PATH, media_type="image/jpeg")

# =====================================================
# API — DOOR CODE
# =====================================================

@router.get("/api/door-code")
async def get_door_code(_: bool = Depends(require_admin)):
    if os.path.exists(CODE_FILE):
        with open(CODE_FILE, "r") as f:
            return json.load(f)
    return {"code": load_door_code()}

@router.post("/api/door-code")
async def set_door_code(d: DoorCode, _: bool = Depends(require_admin)):
    with open(CODE_FILE, "w") as f:
        json.dump({"code": d.code}, f)
    return {"ok": True}

# =====================================================
# API — DESCRIPTION
# =====================================================

@router.get("/api/description")
async def get_description():
    if os.path.exists(DESC_FILE):
        with open(DESC_FILE, "r") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("")

@router.post("/api/description")
async def set_description(d: Description, _: bool = Depends(require_admin)):
    with open(DESC_FILE, "w") as f:
        f.write(d.text)
    return {"ok": True}
