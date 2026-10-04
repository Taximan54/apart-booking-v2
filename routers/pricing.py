"""API: цены и промокоды."""
import json
import os
from fastapi import APIRouter, Depends

from core.auth import require_admin
from core.constants import PRICE_FILE, DEFAULT_PRICES, PROMO_FILE
from core.models import Prices, PromoCodes, PromoValidate

router = APIRouter()


# =====================================================
# API — PRICES
# =====================================================

@router.get("/api/prices")
async def get_prices():
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_PRICES, **saved}
    return DEFAULT_PRICES

@router.post("/api/prices")
async def set_prices(p: Prices, _: bool = Depends(require_admin)):
    with open(PRICE_FILE, "w") as f:
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
