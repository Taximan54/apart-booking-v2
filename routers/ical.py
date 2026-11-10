"""API: синхронизация календарей с площадками (Авито, Яндекс Путешествия, Суточно.ру и другими) по iCal."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core.auth import require_admin
from core.ical_sync import (
    IntegrationError,
    MAX_PLATFORMS,
    PRESETS,
    add_platform,
    build_export_feed,
    delete_platform,
    export_url,
    find_platform_by_token,
    get_platform,
    list_platforms,
    regenerate_token,
    sync_all,
    sync_platform,
    update_platform,
)
from core.logger import get_logger
from core.models import CalendarPlatformCreate, CalendarPlatformUpdate
from core.properties import admin_property_id
from services.booking_service import DEFAULT_PROPERTY_ID

logger = get_logger(__name__)

router = APIRouter()


def _view(platform: dict) -> dict:
    """Площадка для админки (токен отдаётся только внутри готовой ссылки)."""
    return {
        "source": platform["source"],
        "name": platform["name"],
        "url": platform["url"],
        "enabled": platform.get("enabled", True),
        "export_url": export_url(platform),
        "last_sync": platform.get("last_sync"),
    }


def _pid(value) -> int:
    """Номер объекта. При прямом вызове функции без FastAPI (например, из теста) — основной объект."""
    return value if isinstance(value, int) else DEFAULT_PROPERTY_ID


def _state(property_id: int) -> dict:
    property_id = _pid(property_id)
    return {"platforms": [_view(p) for p in list_platforms(property_id)], "presets": PRESETS, "max_platforms": MAX_PLATFORMS}


def _bad_request(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/ical/{filename}")
async def public_calendar(filename: str):
    """Наш календарь занятости одного объекта для одной площадки. Доступен только по секретной ссылке этой площадки."""
    found = find_platform_by_token(filename[:-4]) if filename.endswith(".ics") and len(filename) > 4 else None
    if not found:
        raise HTTPException(status_code=404, detail="Not Found")
    property_id, platform = found
    return Response(
        content=build_export_feed(platform["source"], property_id=property_id),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/admin/integrations/calendars")
async def get_calendars(_: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    return _state(property_id)


@router.post("/api/admin/integrations/calendars")
async def add_calendar(data: CalendarPlatformCreate, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    try:
        add_platform(data.name, data.source, property_id)
    except IntegrationError as e:
        _bad_request(e)
    return _state(property_id)


@router.put("/api/admin/integrations/calendars/{source}")
async def update_calendar(source: str, data: CalendarPlatformUpdate, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    try:
        await asyncio.to_thread(update_platform, source, data.name, data.url, data.enabled, property_id)
    except IntegrationError as e:
        _bad_request(e)
    return _state(property_id)


@router.delete("/api/admin/integrations/calendars/{source}")
async def delete_calendar(source: str, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    try:
        removed = delete_platform(source, property_id)
    except IntegrationError as e:
        _bad_request(e)
    return {**_state(property_id), "removed_blocks": removed}


@router.post("/api/admin/integrations/calendars/sync-all")
async def sync_all_calendars(_: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    reports = await asyncio.to_thread(lambda: sync_all(False, property_id=property_id))
    return {**_state(property_id), "reports": reports}


@router.post("/api/admin/integrations/calendars/{source}/sync")
async def sync_calendar(source: str, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    property_id = _pid(property_id)
    if not get_platform(source, property_id):
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    report = await asyncio.to_thread(lambda: sync_platform(source, property_id=property_id))
    return {**_state(property_id), "report": report}


@router.post("/api/admin/integrations/calendars/{source}/regenerate-token")
async def regenerate_calendar_token(source: str, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    """Новая ссылка на наш календарь для площадки: старая перестаёт работать."""
    property_id = _pid(property_id)
    try:
        regenerate_token(source, property_id)
    except IntegrationError as e:
        _bad_request(e)
    return _state(property_id)
