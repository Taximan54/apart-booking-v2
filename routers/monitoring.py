"""API: мониторинг сбоев (админка) и адрес /health/deep для внешней проверки."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import monitoring
from core.auth import require_admin, require_permission

router = APIRouter()


class MonitoringSettings(BaseModel):
    enabled: Optional[bool] = None
    ical_hours: Optional[int] = None
    backup_hours: Optional[int] = None
    disk_free_percent: Optional[int] = None
    remind_hours: Optional[int] = None


@router.get("/api/admin/monitoring")
async def get_monitoring(_=Depends(require_permission("monitoring.view"))):
    return monitoring.public_state()


@router.post("/api/admin/monitoring")
async def set_monitoring(data: MonitoringSettings, _=Depends(require_permission("monitoring.view"))):
    monitoring.save_settings(data.dict(exclude_none=True))
    return monitoring.public_state()


@router.post("/api/admin/monitoring/run")
async def run_monitoring(_=Depends(require_permission("monitoring.view"))):
    """Проверить прямо сейчас (не ждать 5 минут)."""
    names = monitoring.running_task_names()
    return await asyncio.to_thread(monitoring.run_checks, names)


@router.post("/api/admin/monitoring/test")
async def test_monitoring_mail(_=Depends(require_permission("monitoring.view"))):
    return await asyncio.to_thread(monitoring.send_test)


@router.api_route("/health/deep", methods=["GET", "HEAD"])   # HEAD нужен внешним проверкам (UptimeRobot)
async def health_deep():
    """
    Для внешнего сервиса (например, UptimeRobot): 200, если база отвечает и места на диске достаточно,
    иначе 503. Подробностей наружу не отдаёт.
    ВАЖНО: публичный, без require_admin/require_permission — UptimeRobot шлёт запросы без токена.
    """
    problems = monitoring._check_db() + monitoring._check_disk(monitoring.load_settings())
    body = {"status": "problem" if problems else "ok", "incidents": monitoring.open_incident_count()}
    return JSONResponse(body, status_code=503 if problems else 200)