"""Точка входа: приложение FastAPI, подключение роутеров, запуск и остановка."""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.runtime import bot, dp
from core.scheduler import send_notifications
from routers import pages, admin_auth, pricing, content, photos, contracts, bookings, signing_api
from services.booking_service import init_db
from core.logger import get_logger
import core.telegram_callbacks  # noqa: F401  (регистрирует обработчики кнопок Telegram на dp)

logger = get_logger(__name__)

try:
    import pillow_heif
    pillow_heif.register_heif_opener()  # чтобы Image.open() понимал .heic/.heif с iPhone
except ImportError:
    logger.warning("pillow-heif не установлен — фото паспорта в формате HEIC (iPhone) "
          "не будут прикрепляться. Установите: pip install pillow-heif --break-system-packages")

init_db()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")



app.include_router(pages.router)
app.include_router(admin_auth.router)
app.include_router(pricing.router)
app.include_router(content.router)
app.include_router(photos.router)
app.include_router(contracts.router)
app.include_router(bookings.router)
app.include_router(signing_api.router)

# =====================================================
# STARTUP / SHUTDOWN
# =====================================================

@app.on_event("startup")
async def startup():
    logger.info("APPLICATION STARTED")
    async def safe_polling():
        while True:
            try:
                await dp.start_polling(bot)
            except Exception as e:
                logger.error("Bot polling error: " + str(e), exc_info=True)
                await asyncio.sleep(30)
    asyncio.create_task(safe_polling())
    asyncio.create_task(send_notifications())
    logger.info("SCHEDULER STARTED")

@app.on_event("shutdown")
async def shutdown():
    logger.info("APPLICATION STOPPED")
    await bot.session.close()


# --- Совместимость -------------------------------------------------------
# Раньше весь код жил в main.py. Если где-то (например, в handlers/ или services/)
# встречается `from main import имя`, оно по-прежнему работает: имя ищется в новых модулях.
import importlib as _importlib
_COMPAT_MODULES = ['core.runtime', 'core.models', 'core.constants', 'core.auth', 'core.mailer', 'core.contract_docs', 'core.signing', 'core.data_store', 'core.db', 'routers.pages', 'routers.admin_auth', 'routers.pricing', 'routers.content', 'routers.photos', 'core.backup', 'core.passports', 'routers.contracts', 'routers.bookings', 'core.validators', 'routers.signing_api', 'core.telegram_callbacks', 'core.scheduler']
def __getattr__(name):
    for _m in _COMPAT_MODULES:
        _mod = _importlib.import_module(_m)
        if hasattr(_mod, name):
            return getattr(_mod, name)
    raise AttributeError(f"module 'main' has no attribute {name!r}")
