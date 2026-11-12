"""API: чат-помощник (популярные вопросы и ответы). Публичная выдача для сайта и настройки для админки."""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import chat_faq
from core.auth import require_admin
from core.properties import admin_property_id, public_property_id

router = APIRouter()


class ChatItem(BaseModel):
    id: str = ""
    visible: bool = True
    question: str = ""
    answer: str = ""


class ChatFaqUpdate(BaseModel):
    enabled: bool = False
    title: str = ""
    greeting: str = ""
    items: List[ChatItem] = []


@router.get("/api/chat-faq")
async def public_chat_faq(property_id: int = Depends(public_property_id)):
    """Для сайта: вопросы и ответы объекта (или {"enabled": false}, если чат выключен)."""
    return chat_faq.public_view(property_id)


@router.get("/api/admin/chat-faq")
async def get_chat_faq(_: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    return chat_faq.admin_view(property_id)


@router.post("/api/admin/chat-faq")
async def set_chat_faq(data: ChatFaqUpdate, _: bool = Depends(require_admin), property_id: int = Depends(admin_property_id)):
    chat_faq.save_settings(property_id, data.dict())
    return chat_faq.admin_view(property_id)
