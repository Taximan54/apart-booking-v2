"""Главная страница, health-check, занятые даты."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from services.booking_service import get_booked_ranges

router = APIRouter()


# =====================================================
# HOME PAGE
# =====================================================

@router.get("/", response_class=HTMLResponse)
async def home():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/api/booked-dates")
async def booked_dates():
    return get_booked_ranges()
