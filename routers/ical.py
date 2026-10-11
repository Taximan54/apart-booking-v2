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
    get_platform,
    list_platforms,
    platform_by_token,
    regenerate_token,
    sync_all,
    sync_platform,
    update_platform,
)
from core.logger import get_logger
from core.models import CalendarPlatformCreate, CalendarPlatformUpdate

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


def _state() -> dict:
    return {"platforms": [_view(p) for p in list_platforms()], "presets": PRESETS, "max_platforms": MAX_PLATFORMS}


def _bad_request(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/ical/{filename}")
async def public_calendar(filename: str):
    """Наш календарь занятости для одной площадки. Доступен только по секретной ссылке этой площадки."""
    platform = platform_by_token(filename[:-4]) if filename.endswith(".ics") and len(filename) > 4 else None
    if not platform:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(
        content=build_export_feed(platform["source"]),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/admin/integrations/calendars")
async def get_calendars(_: bool = Depends(require_admin)):
    return _state()


@router.post("/api/admin/integrations/calendars")
async def add_calendar(data: CalendarPlatformCreate, _: bool = Depends(require_admin)):
    try:
        add_platform(data.name, data.source)
    except IntegrationError as e:
        _bad_request(e)
    return _state()


@router.put("/api/admin/integrations/calendars/{source}")
async def update_calendar(source: str, data: CalendarPlatformUpdate, _: bool = Depends(require_admin)):
    try:
        await asyncio.to_thread(update_platform, source, data.name, data.url, data.enabled)
    except IntegrationError as e:
        _bad_request(e)
    return _state()


@router.delete("/api/admin/integrations/calendars/{source}")
async def delete_calendar(source: str, _: bool = Depends(require_admin)):
    try:
        removed = delete_platform(source)
    except IntegrationError as e:
        _bad_request(e)
    return {**_state(), "removed_blocks": removed}


@router.post("/api/admin/integrations/calendars/sync-all")
async def sync_all_calendars(_: bool = Depends(require_admin)):
    reports = await asyncio.to_thread(sync_all, False)
    return {**_state(), "reports": reports}


@router.post("/api/admin/integrations/calendars/{source}/sync")
async def sync_calendar(source: str, _: bool = Depends(require_admin)):
    if not get_platform(source):
        raise HTTPException(status_code=404, detail="Площадка не найдена")
    report = await asyncio.to_thread(sync_platform, source)
    return {**_state(), "report": report}


@router.post("/api/admin/integrations/calendars/{source}/regenerate-token")
async def regenerate_calendar_token(source: str, _: bool = Depends(require_admin)):
    """Новая ссылка на наш календарь для площадки: старая перестаёт работать."""
    try:
        regenerate_token(source)
    except IntegrationError as e:
        _bad_request(e)
    return _state()
