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
from core.models import Prices, PromoCodes, PromoValidate, ReviewPromoTest, ReviewPromoUpdate
from core.properties import admin_property_id, property_file, request_property_id
from core.review_promo import (
    REVIEW_DECISIONS,
    build_review_email,
    get_review_settings,
    load_review_decisions,
    load_review_template_text,
    save_review_settings,
    set_review_decision,
)

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
