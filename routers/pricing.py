"""API: цены и промокоды."""
import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_admin
from core.constants import (
    DEFAULT_PRICES,
    DEFAULT_REVIEW_SUBJECT,
    DEFAULT_REVIEW_TEMPLATE,
    PRICE_FILE,
    PROMO_FILE,
    REVIEW_FILE,
)
from core.bookings_repo import exists_by_ref
from core.landlord import get_landlord_email
from core.mailer import send_email
from core.models import Prices, PromoCodes, PromoValidate, ReviewPromoSend, ReviewPromoTest, ReviewPromoUpdate
from core.logger import get_logger
from core.properties import admin_property_id, property_file, request_property_id
from core.review_promo import (
    MAX_PERCENT,
    REVIEW_DECISIONS,
    build_review_email,
    get_review_settings,
    issue_personal_promo_code,
    load_promo_codes,
    load_review_decisions,
    load_review_template_text,
    remove_promo_code,
    save_review_settings,
    set_review_decision,
)

logger = get_logger(__name__)

router = APIRouter()


# =====================================================
# API — PRICES
# =====================================================

@router.get("/api/prices")
async def get_prices(property_id: int = Depends(request_property_id)):
    if os.path.exists(property_file(PRICE_FILE, property_id)):
        with open(property_file(PRICE_FILE, property_id), "r") as f:
            saved = json.load(f)
        return {**DEFAULT_PRICES, **saved}
    return DEFAULT_PRICES

@router.post("/api/prices")
async def set_prices(p: Prices, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    with open(property_file(PRICE_FILE, property_id), "w") as f:
        json.dump(p.dict(), f, ensure_ascii=False)
    return {"ok": True}

# =====================================================
# API — PROMO CODES
# =====================================================

@router.get("/api/promo-codes")
async def get_promo_codes(_: bool = Depends(require_admin)):
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@router.post("/api/promo-codes")
async def set_promo_codes(p: PromoCodes, _: bool = Depends(require_admin)):
    # Нормализуем коды в верхний регистр — чтобы ввод не зависел от регистра
    normalized = {
        code.strip().upper(): percent
        for code, percent in p.codes.items()
        if code.strip()
    }
    with open(PROMO_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False)
    return {"ok": True}

@router.post("/api/promo-codes/validate")
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
# API — ПИСЬМО ПОСЛЕ ВЫЕЗДА (отзыв + промокод)
# =====================================================

@router.get("/api/admin/review-promo")
async def get_review_promo(_: bool = Depends(require_admin)):
    """Размер скидки, тема и текст письма после выезда."""
    return {**get_review_settings(), "text": load_review_template_text(), "default_text": DEFAULT_REVIEW_TEMPLATE,
            "default_subject": DEFAULT_REVIEW_SUBJECT}


@router.post("/api/admin/review-promo")
async def set_review_promo(data: ReviewPromoUpdate, _: bool = Depends(require_admin)):
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Текст письма не может быть пустым")
    try:
        settings = save_review_settings(data.percent, data.subject)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        f.write(data.text)
    return {**settings, "text": data.text}


@router.post("/api/admin/review-promo/test")
async def send_review_promo_test(data: ReviewPromoTest, _: bool = Depends(require_admin)):
    """Пробное письмо (с тестовым именем и кодом) на указанную почту или на почту из «Контактов»."""
    to = (data.email or "").strip() or get_landlord_email()
    if "@" not in to or " " in to or len(to) > 200:
        raise HTTPException(status_code=400, detail="Укажите корректный адрес почты")
    settings = get_review_settings()
    subject, html, text = build_review_email("Иван", "RETURNTEST" if settings["percent"] > 0 else "", settings["percent"])
    await asyncio.to_thread(send_email, to, subject, html, None, text)
    return {"ok": True, "to": to}


@router.post("/api/admin/review-promo/send")
async def send_promo_to_guest(data: ReviewPromoSend, _: bool = Depends(require_admin)):
    """
    Письмо с промокодом любому человеку (например, гостю, который жил до запуска сайта, через другую площадку).
    Промокод — существующий (поле code) или новый личный (скидка percent). Текст и тема — стандартные
    из настроек письма после выезда или свои.
    """
    to = (data.email or "").strip()
    if "@" not in to or " " in to or len(to) > 200:
        raise HTTPException(status_code=400, detail="Укажите корректный адрес почты")
    name = (data.name or "").strip()[:80]
    subject = (data.subject or "").strip()
    if len(subject) > 150:
        raise HTTPException(status_code=400, detail="Тема письма слишком длинная (макс. 150 символов)")
    text = (data.text or "").strip()

    code = (data.code or "").strip().upper()
    created = False
    if code:
        percent = load_promo_codes().get(code)
        if not isinstance(percent, int) or percent <= 0:
            raise HTTPException(status_code=400, detail="Такого промокода нет или у него нет скидки")
    else:
        percent = data.percent
        if not 1 <= percent <= MAX_PERCENT:
            raise HTTPException(status_code=400, detail=f"Скидка должна быть от 1 до {MAX_PERCENT}%")
        try:
            code = issue_personal_promo_code(percent)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        created = True

    letter_subject, html, plain = build_review_email(name, code, percent, template_text=text or None, subject=subject or None)
    try:
        await asyncio.to_thread(send_email, to, letter_subject, html, None, plain)
    except Exception as e:
        logger.warning("Не удалось отправить промокод %s: %s", code, e)
        if created:
            remove_promo_code(code)   # письмо не ушло — новый промокод не оставляем
        raise HTTPException(status_code=502, detail="Не удалось отправить письмо. Проверьте адрес и настройки почты")
    logger.info("Промокод %s (скидка %s%%) отправлен письмом", code, percent)
    return {"ok": True, "to": to, "code": code, "percent": percent, "created": created}


class ReviewDecision(BaseModel):
    decision: str


@router.get("/api/admin/review-decisions")
async def get_review_decisions(_: bool = Depends(require_admin)):
    """Решения админа по письму после выезда: {номер брони: promo | nopromo | skip}."""
    return load_review_decisions()


@router.post("/api/admin/bookings/{ref}/review-decision")
async def set_booking_review_decision(ref: str, data: ReviewDecision, _: bool = Depends(require_admin)):
    """Админ решает, отправлять ли гостю письмо после выезда (с промокодом / без / не отправлять)."""
    if data.decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=400, detail="Неверное решение")
    if not exists_by_ref(ref):
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    set_review_decision(ref, data.decision)
    return {"ok": True}
