"""Главная страница, health-check, занятые даты."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from core.properties import get_property_by_slug, public_property_id
from services.booking_service import get_booked_ranges

router = APIRouter()


# =====================================================
# HOME PAGE
# =====================================================

@router.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@router.get("/o/{slug}", response_class=HTMLResponse)
async def property_page(slug: str):
    """Страница отдельного объекта (квартиры): тот же сайт, данные берутся по адресу страницы объекта."""
    prop = get_property_by_slug(slug)
    if not prop or not prop["active"]:
        raise HTTPException(status_code=404, detail="Объект не найден")
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/api/booked-dates")
async def booked_dates(property_id: int = Depends(public_property_id)):
    return get_booked_ranges(property_id)
