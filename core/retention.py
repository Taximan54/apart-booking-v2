"""Хранение данных брони: упаковка договоров и фото паспортов в архив с паролем и удаление по сроку.

Три независимые настройки (файл RETENTION_FILE, по умолчанию всё выключено):
  pack_days        — через сколько дней ПОСЛЕ ВЫЕЗДА файлы подтверждённой брони упаковываются в архив
                     с паролем (обычные файлы удаляются). Только если залог отмечен возвращённым. 0 — выключено.
  delete_days      — через сколько дней после выезда упакованный архив удаляется насовсем. 0 — не удалять.
  purge_cancelled  — удалять файлы ОТМЕНЁННЫХ броней, у которых договор не был подписан.
Отменённые брони с подписанным договором не трогаются (решение по возврату предоплаты пока не принято).
Пароль архива — тот же, что у резервных копий. Без пароля упаковка не запускается.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from core import passports as _passports
from core.constants import ARCHIVE_DIR, CONTRACTS_DIR, PASSPORT_DIR, RETENTION_FILE
from core.db import booking_ref_alt, get_db
from core.logger import get_logger

logger = get_logger(__name__)

CONTRACT_SUFFIXES = (".txt", ".pdf", "_podpisan.pdf", "_soglasie_pd.pdf")
CONFIRMED_STATUSES = ("confirmed", "fully_paid")
MAX_DAYS = 3650
CHECK_EVERY_SECONDS = 3600      # как часто проверяем (раз в час)
FIRST_RUN_DELAY = 120           # после запуска сервера первую проверку делаем через 2 минуты
MAX_PACKS_PER_RUN = 20          # за один заход упаковываем не больше стольких броней

_password_warned = False


# =====================================================
# НАСТРОЙКИ
# =====================================================

def _clamp_days(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_DAYS, n))


def validate_settings(pack_days, delete_days, purge_cancelled) -> dict:
    p, d = _clamp_days(pack_days), _clamp_days(delete_days)
    if p > 0 and d > 0 and d < p:
        raise ValueError("Срок хранения архива не может быть меньше срока упаковки")
    return {"pack_days": p, "delete_days": d, "purge_cancelled": bool(purge_cancelled)}


def load_settings() -> dict:
    try:
        with open(RETENTION_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    return {
        "pack_days": _clamp_days(raw.get("pack_days", 0)),
        "delete_days": _clamp_days(raw.get("delete_days", 0)),
        "purge_cancelled": bool(raw.get("purge_cancelled", False)),
    }


def save_settings(pack_days, delete_days, purge_cancelled) -> dict:
    s = validate_settings(pack_days, delete_days, purge_cancelled)
    os.makedirs(os.path.dirname(RETENTION_FILE), exist_ok=True)
    with open(RETENTION_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f)
    return s


def _password() -> str:
    from core.backup import get_backup_password   # пароль резервных копий (config.py или backup_password.txt)
    return get_backup_password()


def password_is_set() -> bool:
    try:
        return bool(_password())
    except Exception:
        return False


def _today():
    from core.runtime import now_nsk
    return now_nsk().date()


def _d(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# =====================================================
# ИНДЕКС АРХИВОВ (ARCHIVE_DIR/index.json): {ref: {check_out, packed_at, archives: [имена файлов]}}
# =====================================================

def _index_path() -> str:
    return os.path.join(ARCHIVE_DIR, "index.json")


def _load_index() -> dict:
    try:
        with open(_index_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_index(index: dict) -> None:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    os.replace(tmp, _index_path())


def list_archived() -> dict:
    """Упакованные брони для админки: {ref: {check_out, packed_at, archives}}."""
    return _load_index()


# =====================================================
# ФАЙЛЫ БРОНИ
# =====================================================

def _variants(ref: str):
    return list(dict.fromkeys((ref, booking_ref_alt(ref))))


def _contract_files(ref: str):
    """[(имя_в_архиве, путь)] — файлы договоров брони (черновик, PDF, подписанный договор, согласие)."""
    found, seen = [], set()
    for cand in _variants(ref):
        for suffix in CONTRACT_SUFFIXES:
            name = cand + suffix
            path = os.path.join(CONTRACTS_DIR, name)
            if name not in seen and os.path.isfile(path):
                seen.add(name)
                found.append(("contracts/" + name, path))
    return found


def _passport_files(ref: str):
    """(ключи записи в привязках, [(имя_в_архиве, путь)], {ключ: запись}) — фото паспорта брони."""
    pm = _passports.load_passport_map()
    keys, photos, entries, seen = [], [], {}, set()
    for cand in _variants(ref):
        entry = pm.get(cand)
        if not isinstance(entry, dict):
            continue
        keys.append(cand)
        entries[cand] = entry
        for fname in entry.values():
            if not fname or fname in seen:
                continue
            path = os.path.join(PASSPORT_DIR, fname)
            if os.path.isfile(path):
                seen.add(fname)
                photos.append(("passports/" + fname, path))
    return keys, photos, entries


def _has_files(ref: str) -> bool:
    return bool(_contract_files(ref)) or bool(_passport_files(ref)[1])


def _is_signed(ref: str, row: dict) -> bool:
    if (row.get("signed_at") or "").strip():
        return True
    return any(os.path.isfile(os.path.join(CONTRACTS_DIR, c + "_podpisan.pdf")) for c in _variants(ref))


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Не удалось удалить файл %s: %s", path, e)


def purge_booking_files(ref: str) -> int:
    """Удаляет файлы договоров и фото паспорта брони и запись о фото. Возвращает число удалённых файлов."""
    files = [p for _, p in _contract_files(ref)]
    keys, photos, _ = _passport_files(ref)
    files += [p for _, p in photos]
    for path in files:
        _remove(path)
    if keys:
        pm = _passports.load_passport_map()
        for k in keys:
            pm.pop(k, None)
        _passports.save_passport_map(pm)
    return len(files)


# =====================================================
# УПАКОВКА В АРХИВ С ПАРОЛЕМ
# =====================================================

def _free_archive_path(ref: str) -> str:
    safe = re.sub(r"[^\w\-]", "_", ref)
    path = os.path.join(ARCHIVE_DIR, safe + ".zip")
    n = 2
    while os.path.exists(path):   # новый архив той же брони никогда не затирает старый
        path = os.path.join(ARCHIVE_DIR, f"{safe}_{n}.zip")
        n += 1
    return path


def _write_archive(path: str, password: str, items, meta: dict) -> None:
    import pyzipper
    with pyzipper.AESZipFile(path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode("utf-8"))
        for arcname, src in items:
            zf.write(src, arcname=arcname)
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))


def _verify_archive(path: str, password: str, items) -> bool:
    """Архив открывается с паролем, не повреждён, зашифрован, и в нём все файлы с теми же размерами."""
    try:
        import pyzipper
        with pyzipper.AESZipFile(path) as zf:
            zf.setpassword(password.encode("utf-8"))
            if zf.testzip() is not None:
                return False
            infos = {i.filename: i for i in zf.infolist()}
            if not infos or not all(i.flag_bits & 0x1 for i in infos.values()):
                return False
            for arcname, src in items:
                info = infos.get(arcname)
                if info is None or info.file_size != os.path.getsize(src):
                    return False
        return True
    except Exception as e:
        logger.warning("Проверка архива %s не пройдена: %s", path, e)
        return False


def pack_booking(ref: str, check_out: str, password: str):
    """
    Упаковывает файлы брони в один архив с паролем. Обычные файлы удаляются ТОЛЬКО после того,
    как архив записан и проверен. Возвращает путь к архиву или None, если упаковывать было нечего.
    """
    files = _contract_files(ref)
    keys, photos, entries = _passport_files(ref)
    items = files + photos
    if not items:
        return None
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    final = _free_archive_path(ref)
    tmp = final + ".tmp"
    packed_at = _today().strftime("%Y-%m-%d")
    meta = {"ref": ref, "check_out": check_out, "packed_at": packed_at, "passport_map": entries}
    try:
        _write_archive(tmp, password, items, meta)
        if not _verify_archive(tmp, password, items):
            raise RuntimeError("архив не прошёл проверку")
        os.replace(tmp, final)
    except Exception:
        _remove(tmp)
        raise
    # архив готов и проверен — теперь убираем обычные файлы
    for _, src in items:
        _remove(src)
    if keys:
        pm = _passports.load_passport_map()
        for k in keys:
            pm.pop(k, None)
        _passports.save_passport_map(pm)
    index = _load_index()
    entry = index.get(ref) or {"check_out": check_out, "packed_at": packed_at, "archives": []}
    entry["archives"].append(os.path.basename(final))
    index[ref] = entry
    _save_index(index)
    return final


def delete_archive(ref: str) -> int:
    """Удаляет упакованные архивы брони и запись о них. Возвращает число удалённых архивов."""
    index = _load_index()
    removed, changed = 0, False
    for cand in _variants(ref):
        if cand not in index:
            continue
        changed = True
        for name in index.pop(cand).get("archives", []):
            path = os.path.join(ARCHIVE_DIR, os.path.basename(name))
            if os.path.exists(path):
                _remove(path)
                removed += 1
    if changed:
        _save_index(index)
    return removed


# =====================================================
# КТО ПОПАДАЕТ ПОД ПРАВИЛА
# =====================================================

def _rows():
    conn = get_db()
    try:
        cur = conn.execute(
            "SELECT id, username, status, check_out, deposit_returned, signed_at FROM bookings "
            "WHERE COALESCE(username,'') <> ''")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _pack_candidates(pack_days: int, today):
    """Подтверждённые брони, залог возвращён, выезд был больше pack_days дней назад и есть что упаковывать."""
    if pack_days <= 0:
        return []
    out = []
    for r in _rows():
        if r["status"] not in CONFIRMED_STATUSES or not r["deposit_returned"]:
            continue
        co = _d(r["check_out"])
        if not co or co + timedelta(days=pack_days) > today:
            continue
        if _has_files(r["username"]):
            out.append(r)
    return out


def _purge_candidates():
    """Отменённые брони без подписанного договора, у которых ещё есть файлы."""
    out = []
    for r in _rows():
        if r["status"] != "cancelled" or _is_signed(r["username"], r):
            continue
        if _has_files(r["username"]):
            out.append(r)
    return out


def _archives_due(delete_days: int, today):
    if delete_days <= 0:
        return []
    due = []
    for ref, entry in _load_index().items():
        base = _d(entry.get("check_out")) or _d(entry.get("packed_at"))
        if base and base + timedelta(days=delete_days) <= today:
            due.append(ref)
    return due


def archive_delete_date(entry: dict, delete_days: int):
    """Дата удаления архива (ДД.ММ.ГГГГ) или пустая строка, если архивы не удаляются."""
    if delete_days <= 0:
        return ""
    base = _d(entry.get("check_out")) or _d(entry.get("packed_at"))
    if not base:
        return ""
    return (base + timedelta(days=delete_days)).strftime("%d.%m.%Y")


def preview(pack_days, delete_days, purge_cancelled=False) -> dict:
    """Сколько броней попадёт под правила при указанных значениях (без сохранения и без изменений)."""
    today = _today()
    s = validate_settings(pack_days, delete_days, purge_cancelled)
    return {
        "to_pack": len(_pack_candidates(s["pack_days"], today)),
        "archives_to_delete": len(_archives_due(s["delete_days"], today)),
        "cancelled_with_files": len(_purge_candidates()),
    }


# =====================================================
# ЗАПУСК
# =====================================================

def run_retention() -> dict:
    global _password_warned
    s = load_settings()
    today = _today()
    result = {"packed": 0, "archives_deleted": 0, "purged": 0, "errors": 0}

    if s["purge_cancelled"]:
        for r in _purge_candidates():
            try:
                n = purge_booking_files(r["username"])
                result["purged"] += 1
                logger.info("Отменённая бронь %s: удалено файлов %s", r["username"], n)
            except Exception as e:
                result["errors"] += 1
                logger.error("Не удалось очистить файлы отменённой брони %s: %s", r["username"], e, exc_info=True)

    if s["pack_days"] > 0:
        candidates = _pack_candidates(s["pack_days"], today)
        if candidates:
            password = ""
            try:
                password = _password()
            except Exception as e:
                logger.error("Не удалось получить пароль архивов: %s", e)
            if not password:
                if not _password_warned:
                    logger.error("Упаковка брони в архив не запущена: пароль резервных копий не задан "
                                 "(BACKUP_PASSWORD в config.py или файл backup_password.txt)")
                    _password_warned = True
            else:
                for r in candidates[:MAX_PACKS_PER_RUN]:
                    try:
                        if pack_booking(r["username"], r["check_out"], password):
                            result["packed"] += 1
                            logger.info("Бронь %s упакована в архив с паролем", r["username"])
                    except Exception as e:
                        result["errors"] += 1
                        logger.error("Не удалось упаковать бронь %s (файлы оставлены как есть): %s", r["username"], e, exc_info=True)

    if s["delete_days"] > 0:
        for ref in _archives_due(s["delete_days"], today):
            try:
                if delete_archive(ref):
                    result["archives_deleted"] += 1
                    logger.info("Архив брони %s удалён по сроку хранения", ref)
            except Exception as e:
                result["errors"] += 1
                logger.error("Не удалось удалить архив брони %s: %s", ref, e, exc_info=True)

    return result


async def retention_loop():
    await asyncio.sleep(FIRST_RUN_DELAY)
    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception as e:
            logger.error("Хранение данных брони: %s", e, exc_info=True)
        await asyncio.sleep(CHECK_EVERY_SECONDS)
