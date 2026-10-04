"""API: фотографии (галерея, обложка, места, акции) и защищённые фото паспортов."""
import io
import json
import os
import secrets
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import Response
from PIL import Image

from core.auth import require_admin
from core.constants import PHOTOS_ORDER_FILE, PHOTOS_DIR, PASSPORT_DIR
from core.data_store import load_discounts, get_site_settings_dict, load_places, load_properties
from core.models import PhotoOrder, PhotoLabel
from core.passports import compress_passport_image, load_passport_map, apply_passport_watermark

router = APIRouter()


# =====================================================
# API — PHOTOS
# =====================================================

def load_photos_order_data():
    """Читает photos_order.json, гарантируя наличие всех ключей."""
    order_data = {"order": [], "labels": {}, "purpose": {}}
    if os.path.exists(PHOTOS_ORDER_FILE):
        with open(PHOTOS_ORDER_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        order_data["order"] = saved.get("order", [])
        order_data["labels"] = saved.get("labels", {})
        order_data["purpose"] = saved.get("purpose", {})
    return order_data

def get_photos_list():
    """Возвращает список фото ГАЛЕРЕИ КВАРТИРЫ в правильном порядке.

    Фото, загруженные с purpose != "gallery" (обложка сайта, фото карты,
    фото мест «Куда сходить») сюда не попадают.
    """
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    all_files = sorted([
        f for f in os.listdir(PHOTOS_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
    ])
    order_data = load_photos_order_data()
    purpose = order_data["purpose"]
    # Старые фото без метки purpose (загружены до этого изменения) по
    # умолчанию считаются галерейными — почистить можно вручную
    # Фото акций (в т.ч. загруженные раньше с меткой gallery) — не галерея квартиры
    discount_files = set()
    for d in load_discounts():
        for key in ("photo", "photo_mobile"):
            if d.get(key):
                discount_files.add(d[key])
    gallery_files = [
        f for f in all_files
        if purpose.get(f, "gallery") == "gallery" and f not in discount_files
    ]
    saved_order = [f for f in order_data["order"] if f in gallery_files]
    order = saved_order + [f for f in gallery_files if f not in saved_order]
    labels = order_data["labels"]
    return [
        {"filename": f, "url": f"/data/photos/{f}", "label": labels.get(f, f)}
        for f in order
    ]

@router.get("/api/photos")
async def list_photos():
    """Публичный — список фото для галереи квартиры."""
    return get_photos_list()

@router.post("/api/photos/upload")
async def upload_photo(
    file: UploadFile = File(...),
    label: str = Form(""),
    purpose: str = Form("gallery"),
    _: bool = Depends(require_admin)
):
    """Загрузка нового фото. purpose: gallery / site / place / discount."""
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "photo.jpg")[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="Поддерживаются только jpg, png, webp")
    if purpose not in ("gallery", "site", "place", "discount"):
        purpose = "gallery"
    filename = f"photo_{secrets.token_hex(6)}{ext}"
    filepath = os.path.join(PHOTOS_DIR, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    order_data = load_photos_order_data()
    order_data["purpose"][filename] = purpose
    if purpose == "gallery":
        order_data["order"].append(filename)
    if label:
        order_data["labels"][filename] = label
    with open(PHOTOS_ORDER_FILE, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False)
    return {"ok": True, "filename": filename, "url": f"/data/photos/{filename}"}

def find_photo_usages(filename):
    """Возвращает список мест использования фото (hero/карта/место/акция), если оно где-то занято."""
    usages = []
    settings = get_site_settings_dict()
    if settings.get("hero_photo") == filename:
        usages.append("обложка сайта (hero-фото)")
    if settings.get("hero_photo_mobile") == filename:
        usages.append("обложка сайта для мобильной версии (hero-фото)")
    if settings.get("map_photo") == filename:
        usages.append("фото карты в разделе «Расположение»")
    for p in load_places():
        if p.get("photo") == filename:
            usages.append(f"место «{p.get('name', '')}» на странице «Куда сходить?»")
    for d in load_discounts():
        if d.get("photo") == filename:
            usages.append(f"акция «{d.get('name', '')}»")
        if d.get("photo_mobile") == filename:
            usages.append(f"акция «{d.get('name', '')}» (мобильная версия)")
    return usages

@router.delete("/api/photos/{filename}")
async def delete_photo(filename: str, force: bool = False, _: bool = Depends(require_admin)):
    """Удаление фото. Если фото используется как hero/карта/фото места — требует force=true."""
    filepath = os.path.join(PHOTOS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Файл не найден")
    usages = find_photo_usages(filename)
    if usages and not force:
        raise HTTPException(
            status_code=409,
            detail="Это фото сейчас используется: " + "; ".join(usages) + ". Удалить всё равно?"
        )
    os.remove(filepath)
    order_data = load_photos_order_data()
    order_data["order"] = [f for f in order_data["order"] if f != filename]
    order_data["labels"].pop(filename, None)
    order_data["purpose"].pop(filename, None)
    with open(PHOTOS_ORDER_FILE, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False)
    return {"ok": True}

@router.post("/api/photos/reorder")
async def reorder_photos(p: PhotoOrder, _: bool = Depends(require_admin)):
    """Изменение порядка фото галереи."""
    order_data = load_photos_order_data()
    order_data["order"] = p.order
    with open(PHOTOS_ORDER_FILE, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False)
    return {"ok": True}

@router.post("/api/photos/{filename}/label")
async def set_photo_label(filename: str, lb: PhotoLabel, _: bool = Depends(require_admin)):
    """Установить подпись к фото."""
    order_data = load_photos_order_data()
    order_data["labels"][filename] = lb.label
    with open(PHOTOS_ORDER_FILE, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False)
    return {"ok": True}

@router.get("/api/admin/properties")
async def get_properties(_: bool = Depends(require_admin)):
    return load_properties()

@router.post("/api/upload-passport-photo")
async def upload_passport_photo(file: UploadFile = File(...)):
    """
    Публичный эндпоинт — гость прикрепляет фото разворота паспорта при
    бронировании (до создания самой брони). Возвращает имя файла, которое
    нужно передать в /api/bookings полем passport_photo.
    """
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 20МБ)")
    try:
        compressed = compress_passport_image(content)
    except Exception as e:
        print(f"Ошибка обработки фото паспорта (файл '{file.filename}', {len(content)} байт): {e}")
        raise HTTPException(status_code=400, detail="Не удалось обработать изображение — попробуйте другое фото (или переснимите не в формате HEIC)")

    os.makedirs(PASSPORT_DIR, exist_ok=True)
    filename = f"passport_{secrets.token_hex(12)}.jpg"
    filepath = os.path.join(PASSPORT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(compressed)

    return {"ok": True, "filename": filename, "size_kb": round(len(compressed) / 1024, 1)}

@router.get("/api/admin/passport-photo/{booking_ref}/{slot}")
async def get_passport_photo(booking_ref: str, slot: str, _: bool = Depends(require_admin)):
    """Просмотр фото паспорта администратором по номеру брони. slot: main / reg1."""
    if slot not in ("main", "reg1"):
        raise HTTPException(status_code=400, detail="Неверный slot")
    pm = load_passport_map()
    entry = pm.get(booking_ref)
    filename = entry.get(slot) if isinstance(entry, dict) else None
    if not filename:
        raise HTTPException(status_code=404, detail="Фото не прикреплено к этой брони")
    filepath = os.path.join(PASSPORT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Файл не найден на диске")
    # Админ (в карточке брони и в архиве) всегда видит фото с защитной сеткой;
    # оригинал на диске остаётся без изменений.
    try:
        with Image.open(filepath) as im:
            marked = apply_passport_watermark(im)
        buf = io.BytesIO()
        marked.save(buf, format="JPEG", quality=88)
    except Exception as e:
        print(f"WARNING: не удалось наложить сетку на фото паспорта {filename}: {e}")
        raise HTTPException(status_code=500, detail="Не удалось подготовить фото")
    return Response(content=buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
