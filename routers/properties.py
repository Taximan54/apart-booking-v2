"""API: объекты (квартиры): список, создание, изменение, удаление."""
from fastapi import APIRouter, Depends, HTTPException

from core import bookings_repo as repo
from core.auth import require_admin
from core.models import PropertyCreate, PropertyUpdate
from core.properties import (
    PropertyError,
    create_property,
    delete_property,
    list_properties,
    update_property,
)
from services.booking_service import DEFAULT_PROPERTY_ID

router = APIRouter()


def _view(prop: dict) -> dict:
    return {**prop, "is_default": prop["id"] == DEFAULT_PROPERTY_ID, "bookings": repo.count_bookings(prop["id"])}


def _state() -> dict:
    return {"properties": [_view(p) for p in list_properties()], "default_id": DEFAULT_PROPERTY_ID}


def _bad_request(e: Exception):
    raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/properties")
async def public_properties():
    """Публичный список действующих объектов (для каталога и переключателя на сайте): без служебных данных."""
    return [
        {"id": p["id"], "name": p["name"], "address": p["address"], "slug": p["slug"], "is_default": p["id"] == DEFAULT_PROPERTY_ID}
        for p in list_properties() if p["active"]
    ]


@router.get("/api/admin/properties")
async def get_properties(_: bool = Depends(require_admin)):
    return _state()


@router.post("/api/admin/properties")
async def add_property(data: PropertyCreate, _: bool = Depends(require_admin)):
    try:
        prop = create_property(data.name, data.address, data.slug)
    except PropertyError as e:
        _bad_request(e)
    return {**_state(), "created_id": prop["id"]}


@router.put("/api/admin/properties/{property_id}")
async def edit_property(property_id: int, data: PropertyUpdate, _: bool = Depends(require_admin)):
    try:
        update_property(property_id, data.name, data.address, data.active, data.slug)
    except PropertyError as e:
        _bad_request(e)
    return _state()


@router.delete("/api/admin/properties/{property_id}")
async def remove_property(property_id: int, _: bool = Depends(require_admin)):
    try:
        delete_property(property_id)
    except PropertyError as e:
        _bad_request(e)
    return _state()
