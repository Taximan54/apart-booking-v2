"""Резервное копирование данных (zip) и отправка копий."""
import asyncio
import json
import os

from config import ADMIN_IDS
from core.constants import (
    BACKUP_LOG_FILE,
    BACKUP_DIR,
    DB_FILE,
    PRICE_FILE,
    CONTACTS_FILE,
    PAYMENT_FILE,
    PROMO_FILE,
    CONTRACT_FILE,
    PASSPORT_MAP_FILE,
    SETTINGS_FILE,
    LANDLORD_FILE,
    DISCOUNTS_FILE,
    PLACES_FILE,
    CONTRACTS_DIR,
    PASSPORT_DIR,
    BACKUP_KEEP_COUNT,
    DEFAULT_CONTACTS,
    LANDLORD_EMAIL,
)
from core.data_store import get_site_settings_dict
from core.mailer import send_email
from core.runtime import now_nsk, bot
from core.logger import get_logger

logger = get_logger(__name__)


# =====================================================
# РЕЗЕРВНОЕ КОПИРОВАНИЕ
# =====================================================

def get_last_backup_date():
    if os.path.exists(BACKUP_LOG_FILE):
        with open(BACKUP_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("last_date", "")
    return ""

def set_last_backup_date(date_str):
    with open(BACKUP_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_date": date_str}, f)

def create_backup_zip():
    """
    Собирает бэкап главной базы (bookings.db), ключевых JSON-настроек,
    ПОДПИСАННЫХ ДОГОВОРОВ (CONTRACTS_DIR) и ФОТО ПАСПОРТОВ (PASSPORT_DIR)
    в один zip-файл, кладёт в BACKUP_DIR, удаляет старые копии сверх
    BACKUP_KEEP_COUNT. Возвращает путь к созданному файлу.
    """
    import zipfile
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = now_nsk().strftime("%Y-%m-%d_%H-%M")
    zip_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.zip")

    files_to_backup = [
        DB_FILE, PRICE_FILE, CONTACTS_FILE, PAYMENT_FILE,
        PROMO_FILE, CONTRACT_FILE, PASSPORT_MAP_FILE,
        SETTINGS_FILE, DISCOUNTS_FILE, PLACES_FILE, LANDLORD_FILE,
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files_to_backup:
            if path and os.path.exists(path):
                zf.write(path, arcname=os.path.basename(path))

        # Договоры и фото паспортов — критичные документы, не подлежат восстановлению
        # из кода, поэтому кладём целиком, каждую папку в свою поддиректорию в архиве
        for folder, arc_prefix in ((CONTRACTS_DIR, "contracts"), (PASSPORT_DIR, "passports")):
            if os.path.isdir(folder):
                for fname in os.listdir(folder):
                    fpath = os.path.join(folder, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, arcname=f"{arc_prefix}/{fname}")

    # Ротация: оставляем только последние BACKUP_KEEP_COUNT файлов
    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_") and f.endswith(".zip")]
    )
    while len(backups) > BACKUP_KEEP_COUNT:
        oldest = backups.pop(0)
        try:
            os.remove(os.path.join(BACKUP_DIR, oldest))
        except Exception as e:
            logger.warning("Не удалось удалить старую резервную копию %s: %s", oldest, e)

    return zip_path

async def send_backup_everywhere(zip_path):
    """Отправляет файл резервной копии в Telegram админам И на почту арендодателя (best-effort, не роняет процесс при ошибке)."""
    from aiogram.types import FSInputFile
    settings = get_site_settings_dict()
    telegram_targets = set(ADMIN_IDS)
    configured_chat_id = settings.get("notify_telegram_chat_id", "").strip()
    if configured_chat_id:
        try:
            telegram_targets.add(int(configured_chat_id))
        except ValueError:
            pass

    file_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    when_str = now_nsk().strftime('%d.%m.%Y %H:%M')
    caption = f"\U0001f4be \u0420\u0435\u0437\u0435\u0440\u0432\u043d\u0430\u044f \u043a\u043e\u043f\u0438\u044f \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445 \u2014 {when_str} ({file_size_mb:.1f} \u041c\u0411)"

    sent_telegram = False
    if file_size_mb > 49:
        logger.warning(f"Backup skipped for Telegram — файл {file_size_mb:.1f}МБ превышает лимит бота (50МБ). Копия осталась только локально/на почте.")
    else:
        for admin_id in telegram_targets:
            try:
                doc = FSInputFile(zip_path)
                await asyncio.wait_for(bot.send_document(admin_id, doc, caption=caption), timeout=60.0)
                sent_telegram = True
            except Exception as e:
                logger.error(f"Backup send to {admin_id} failed: {e}", exc_info=True)

    sent_email = False
    contacts = DEFAULT_CONTACTS
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                contacts = {**DEFAULT_CONTACTS, **json.load(f)}
        except Exception as e:
            logger.warning("Не удалось прочитать контакты для резервной копии: %s", e)
    backup_email = (contacts.get("email") or "").strip() or LANDLORD_EMAIL
    if backup_email and file_size_mb > 20:
        logger.warning(f"Backup skipped for email — файл {file_size_mb:.1f}МБ, вероятно превысит лимит почтового сервера. Проверяйте копию локально на сервере (BACKUP_DIR) или в Telegram.")
    elif backup_email:
        try:
            html = (
                "<div style='font-family:Arial,sans-serif;padding:20px;color:#333'>"
                f"<p>Резервная копия базы данных, настроек, договоров и фото паспортов — {when_str}.</p>"
                "<p>Файл во вложении. Хранить в надёжном месте.</p></div>"
            )
            send_email(
                backup_email, f"Резервная копия — {when_str}", html,
                attachments=[{"filename": os.path.basename(zip_path), "filepath": zip_path}]
            )
            sent_email = True
        except Exception as e:
            logger.error(f"Backup email failed: {e}", exc_info=True)
    return {"telegram": sent_telegram, "email": sent_email}
