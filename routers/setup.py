"""API: чек-лист «Что осталось заполнить» (только чтение)."""
import asyncio

from fastapi import APIRouter, Depends

from core.auth import require_admin
from core.properties import admin_property_id
from core.setup_checklist import build_checklist

router = APIRouter()


@router.get("/api/admin/setup-checklist")
async def get_setup_checklist(_: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    return await asyncio.to_thread(build_checklist, property_id)
