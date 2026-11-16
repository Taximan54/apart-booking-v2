"""Резервное копирование данных (zip) и отправка копий."""
import asyncio
import json
import os
import time
import zipfile

import config
from config import ADMIN_IDS
from core.constants import (
    BACKUP_LOG_FILE,
    BACKUP_PASSWORD_FILE,
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
    ICAL_FILE,
    DISCOUNTS_FILE,
    PLACES_FILE,
    CONTRACTS_DIR,
    PASSPORT_DIR,
    ARCHIVE_DIR,
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

def get_backup_password() -> str:
    """
    Пароль для шифрования резервных копий. Берётся из config.py
    (BACKUP_PASSWORD = "...") или, если там нет, из файла
    backup_password.txt в папке данных. Пустая строка — пароль не задан.
    """
    password = (getattr(config, "BACKUP_PASSWORD", "") or "").strip()
    if password:
        return password
    if os.path.exists(BACKUP_PASSWORD_FILE):
        try:
            with open(BACKUP_PASSWORD_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.warning("Не удалось прочитать файл пароля резервных копий: %s", e)
    return ""

def is_backup_encrypted(zip_path: str) -> bool:
    """True, если в архиве все файлы зашифрованы (архив не откроется без пароля)."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            return bool(infos) and all(i.flag_bits & 0x1 for i in infos)
    except Exception as e:
        logger.warning("Не удалось проверить шифрование копии %s: %s", zip_path, e)
        return False

def _open_backup_archive(zip_path: str, password: str):
    """
    Открывает архив на запись. С паролем — шифрование AES-256 (библиотека
    pyzipper); без пароля или без библиотеки — обычный незашифрованный zip,
    который наружу (почта, Telegram) не отправляется.
    """
    if password:
        try:
            import pyzipper
            zf = pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES)
            zf.setpassword(password.encode("utf-8"))
            return zf
        except ImportError:
            logger.error("Пароль к копиям задан, но библиотека pyzipper не установлена — копия будет без шифрования и не будет отправлена наружу")
    return zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)

# Что НЕ кладём в копию: сам пароль копий (лежать рядом с данными незачем)
_BACKUP_SKIP_FILES = {"backup_password.txt"}
# Папки внутри /data, которые кладём в основную копию целиком (с вложенными): данные объектов № 2, 3…
_BACKUP_EXTRA_DIRS = ("properties",)
# Тяжёлое и редко нужное — отдельными архивами и реже, чем основная копия (интервалы потом уйдут в настройки админки):
#   документы (договоры, паспорта, архив договоров): раз в 14 дней, хранить 3
#   фото квартир: раз в 30 дней, хранить 2
# Основная ежедневная копия (база, настройки, шаблоны) остаётся небольшой и уходит на почту.
_DOCS_PREFIX = "backup_docs_"
_PHOTOS_PREFIX = "backup_photos_"
_DOCS_EVERY_DAYS, _DOCS_KEEP = 14, 3
_PHOTOS_EVERY_DAYS, _PHOTOS_KEEP = 30, 2

def _extra_archive_age_days(prefix: str):
    """Сколько дней назад создан самый свежий архив с этим префиксом, или None, если архивов нет."""
    try:
        times = [os.path.getmtime(os.path.join(BACKUP_DIR, n)) for n in os.listdir(BACKUP_DIR)
                 if n.startswith(prefix) and n.endswith(".zip")]
    except Exception:
        return None
    return max(0.0, (time.time() - max(times)) / 86400) if times else None

def _create_extra_zip(prefix: str, timestamp: str, folders, every_days: int, force: bool):
    """
    Отдельный зашифрованный архив с папками folders [(путь, имя_в_архиве)].
    Создаётся, если последний такой архив старше every_days дней (или его нет), либо при force.
    Нет файлов — архив не создаётся.
    """
    if not force:
        age = _extra_archive_age_days(prefix)
        if age is not None and age < every_days:
            return None
    files = []
    for folder, arc_prefix in folders:
        for cur, _dirs, names in os.walk(folder):
            for fname in sorted(names):
                fpath = os.path.join(cur, fname)
                rel = os.path.relpath(fpath, folder).replace(os.sep, "/")
                files.append((fpath, f"{arc_prefix}/{rel}"))
    if not files:
        return None
    zip_path = os.path.join(BACKUP_DIR, f"{prefix}{timestamp}.zip")
    with _open_backup_archive(zip_path, get_backup_password()) as zf:
        for fpath, arc in files:
            zf.write(fpath, arcname=arc)
    return zip_path

def _rotate(is_mine, keep: int):
    """Оставляет только последние keep архивов, для которых is_mine(имя) истинно."""
    names = sorted(n for n in os.listdir(BACKUP_DIR) if n.startswith("backup_") and n.endswith(".zip") and is_mine(n))
    while len(names) > keep:
        oldest = names.pop(0)
        try:
            os.remove(os.path.join(BACKUP_DIR, oldest))
        except Exception as e:
            logger.warning("Не удалось удалить старую резервную копию %s: %s", oldest, e)

def create_backup_zip(force_all: bool = False):
    """
    Основная копия: база (bookings.db), настройки, шаблоны и все остальные файлы папки данных
    (в т.ч. properties/) — в zip, защищённый паролем (если он задан), в BACKUP_DIR; хранится
    BACKUP_KEEP_COUNT штук. Возвращает путь к ней (только она уходит на почту).
    Отдельными архивами и реже: документы (договоры, паспорта, архив договоров) — backup_docs_<дата>.zip
    и фото квартир — backup_photos_<дата>.zip. force_all=True (кнопка «Копия сейчас») делает их сразу.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = now_nsk().strftime("%Y-%m-%d_%H-%M")
    zip_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.zip")

    files_to_backup = [
        DB_FILE, PRICE_FILE, CONTACTS_FILE, PAYMENT_FILE,
        PROMO_FILE, CONTRACT_FILE, PASSPORT_MAP_FILE,
        SETTINGS_FILE, DISCOUNTS_FILE, PLACES_FILE, LANDLORD_FILE, ICAL_FILE,
    ]
    written = set()   # имена уже добавленных файлов, чтобы не класть дважды
    with _open_backup_archive(zip_path, get_backup_password()) as zf:
        for path in files_to_backup:
            if path and os.path.exists(path):
                arc = os.path.basename(path)
                zf.write(path, arcname=arc)
                written.add(arc)

        # Всё остальное из папки данных: настройки по объектам, каталог, чат-помощник,
        # правила бронирования, мониторинг и т.д. Новые файлы попадают сами.
        data_dir = os.path.dirname(DB_FILE)
        if data_dir and os.path.isdir(data_dir):
            for fname in sorted(os.listdir(data_dir)):
                fpath = os.path.join(data_dir, fname)
                if (os.path.isfile(fpath) and fname not in written
                        and fname not in _BACKUP_SKIP_FILES and ".backup_" not in fname):
                    zf.write(fpath, arcname=fname)
                    written.add(fname)
            for sub in _BACKUP_EXTRA_DIRS:
                root = os.path.join(data_dir, sub)
                for cur, _dirs, files in os.walk(root):
                    for fname in sorted(files):
                        fpath = os.path.join(cur, fname)
                        arc = os.path.relpath(fpath, data_dir).replace(os.sep, "/")
                        if arc not in written and ".backup_" not in fname:
                            zf.write(fpath, arcname=arc)
                            written.add(arc)

    # Документы и фото — отдельными архивами и реже (см. константы выше); сбой не должен ронять основную копию
    try:
        _create_extra_zip(_DOCS_PREFIX, timestamp,
                          [(CONTRACTS_DIR, "contracts"), (PASSPORT_DIR, "passports"), (ARCHIVE_DIR, "contracts_archive")],
                          _DOCS_EVERY_DAYS, force_all)
        _create_extra_zip(_PHOTOS_PREFIX, timestamp,
                          [(os.path.join(os.path.dirname(DB_FILE), "photos"), "photos")],
                          _PHOTOS_EVERY_DAYS, force_all)
    except Exception as e:
        logger.warning("Не удалось создать архив с документами или фото: %s", e)

    # Ротация: основные, документы и фото считаем отдельно
    _rotate(lambda n: not n.startswith((_DOCS_PREFIX, _PHOTOS_PREFIX)), BACKUP_KEEP_COUNT)
    _rotate(lambda n: n.startswith(_DOCS_PREFIX), _DOCS_KEEP)
    _rotate(lambda n: n.startswith(_PHOTOS_PREFIX), _PHOTOS_KEEP)

    return zip_path

async def send_backup_everywhere(zip_path):
    """Отправляет файл резервной копии в Telegram админам И на почту арендодателя (best-effort, не роняет процесс при ошибке)."""
    from aiogram.types import FSInputFile
    if not await asyncio.to_thread(is_backup_encrypted, zip_path):
        logger.error(
            "Резервная копия %s НЕ отправлена: в ней данные гостей, а пароль не задан "
            "(BACKUP_PASSWORD в config.py или файл backup_password.txt). Копия осталась на сервере.",
            os.path.basename(zip_path),
        )
        return {"telegram": False, "email": False, "encrypted": False}
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
                f"<p>Резервная копия базы данных и настроек — {when_str}.</p>"
                "<p>Архив защищён паролем. Файл во вложении, хранить в надёжном месте.</p></div>"
            )
            # SMTP — синхронный, поэтому в отдельном потоке, чтобы сайт не замирал на время загрузки письма
            await asyncio.to_thread(
                send_email,
                backup_email, f"Резервная копия — {when_str}", html,
                attachments=[{"filename": os.path.basename(zip_path), "filepath": zip_path}]
            )
            sent_email = True
        except Exception as e:
            logger.error(f"Backup email failed: {e}", exc_info=True)
    return {"telegram": sent_telegram, "email": sent_email, "encrypted": True}
