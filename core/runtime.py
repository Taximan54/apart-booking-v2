"""Telegram-бот, диспетчер и текущее время объекта."""
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import timezone, timedelta, datetime

from config import BOT_TOKEN
from core.data_store import get_site_settings_dict
from handlers.admin import router as admin_router
from handlers.user import router as user_router


bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
dp.include_router(user_router)
dp.include_router(admin_router)

NSK = timezone(timedelta(hours=7))  # запасное значение, если настройки ещё не загружены


def now_nsk():
    """
    Текущее время в часовом поясе объекта (настраивается в админке —
    Настройки -> Часовой пояс). Влияет на время автоматических рассылок гостям.
    """
    try:
        offset_hours = float(get_site_settings_dict().get("timezone_offset", 7.0))
    except Exception:
        offset_hours = 7.0
    return datetime.now(timezone(timedelta(hours=offset_hours)))
