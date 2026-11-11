"""API: мониторинг сбоев (админка) и адрес /health/deep для внешней проверки."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import monitoring
from core.auth import require_admin

router = APIRouter()


class MonitoringSettings(BaseModel):
    enabled: Optional[bool] = None
    ical_hours: Optional[int] = None
    backup_hours: Optional[int] = None
    disk_free_percent: Optional[int] = None
    remind_hours: Optional[int] = None


@router.get("/api/admin/monitoring")
async def get_monitoring(_: bool = Depends(require_admin)):
    return monitoring.public_state()


@router.post("/api/admin/monitoring")
async def set_monitoring(data: MonitoringSettings, _: bool = Depends(require_admin)):
    monitoring.save_settings(data.dict(exclude_none=True))
    return monitoring.public_state()


@router.post("/api/admin/monitoring/run")
async def run_monitoring(_: bool = Depends(require_admin)):
    """Проверить прямо сейчас (не ждать 5 минут)."""
    names = monitoring.running_task_names()
    return await asyncio.to_thread(monitoring.run_checks, names)


@router.post("/api/admin/monitoring/test")
async def test_monitoring_mail(_: bool = Depends(require_admin)):
    return await asyncio.to_thread(monitoring.send_test)


@router.get("/health/deep")
async def health_deep():
    """
    Для внешнего сервиса (например, UptimeRobot): 200, если база отвечает и места на диске достаточно,
    иначе 503. Подробностей наружу не отдаёт.
    """
    problems = monitoring._check_db() + monitoring._check_disk(monitoring.load_settings())
    body = {"status": "problem" if problems else "ok", "incidents": monitoring.open_incident_count()}
    return JSONResponse(body, status_code=503 if problems else 200)
