"""Авторизация администратора (пароль, токены сессии, роли)."""
import base64
import copy

import hashlib
import hmac
import json
import os
import secrets
import time
from fastapi import Header, HTTPException
from typing import Optional
from core.constants import AUTH_FILE, DATA_DIR

# =====================================================
# ADMIN AUTH
# =====================================================
# Пароль для входа в админку: сначала проверяем /data/admin_auth.json
# (его создаёт смена пароля через саму админку), если файла нет — берём
# ADMIN_PASSWORD из .env. Если ни там, ни там пароля нет — вход запрещён
# для всех (без скрытого дефолтного пароля типа "admin2024").
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# SESSION_SECRET лучше задать в .env, чтобы токены не протухали при каждом
# restart — если не задан, генерируется случайный при каждом старте процесса
# (тогда после любого деплоя придётся перелогиниться в админке).
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
SESSION_TTL    = 60 * 60 * 24 * 7  # токен живёт 7 дней

# Защита от подбора пароля: после LOGIN_MAX_FAILS неверных паролей подряд
# вход с этого адреса блокируется на LOGIN_LOCK_SECONDS. Счётчики хранятся в памяти
# процесса (после перезапуска сервиса сбрасываются).
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 15 * 60

_login_fails = {}  # адрес -> время неверных попыток (за последние 15 минут)


def client_ip(request) -> Optional[str]:
    """Адрес, с которого пришёл запрос (None — запрос без адреса, например прямой вызов в тестах: лимит не применяется)."""
    if request is None:
        return None
    return (request.client.host if request.client else "") or "unknown"


def login_retry_after(ip, now=None) -> int:
    """Сколько секунд ещё действует блокировка входа для адреса (0 — не заблокирован)."""
    if not ip:
        return 0
    now = time.time() if now is None else now
    fails = [t for t in _login_fails.get(ip, []) if now - t < LOGIN_LOCK_SECONDS]
    if fails:
        _login_fails[ip] = fails
    else:
        _login_fails.pop(ip, None)
    if len(fails) >= LOGIN_MAX_FAILS:
        return max(1, int(fails[-1] + LOGIN_LOCK_SECONDS - now) + 1)
    return 0


def register_login_failure(ip, now=None) -> int:
    """Записывает неверный пароль, возвращает число неверных попыток подряд."""
    if not ip:
        return 0
    now = time.time() if now is None else now
    fails = [t for t in _login_fails.get(ip, []) if now - t < LOGIN_LOCK_SECONDS]
    fails.append(now)
    _login_fails[ip] = fails
    if len(_login_fails) > 5000:  # чистка давно устаревших адресов
        for key in [k for k, v in _login_fails.items() if all(now - t >= LOGIN_LOCK_SECONDS for t in v)]:
            del _login_fails[key]
    return len(fails)


def register_login_success(ip) -> None:
    if ip:
        _login_fails.pop(ip, None)


def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except Exception:
        return False


def check_admin_password(password: str) -> bool:
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            stored_hash = json.load(f).get("password_hash", "")
        return verify_password(password, stored_hash)
    # Пароль через панель ещё не задавался — фоллбэк на .env
    return bool(ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)


def make_token(login: Optional[str] = None, fp: str = "") -> str:
    """Токен сессии. Без login — прежний формат (для совместимости со старым входом)."""
    expires = int(time.time()) + SESSION_TTL
    raw_payload = str(expires) if not login else "%s:%s:%s" % (login, fp, expires)
    payload = raw_payload.encode()
    sig = hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload + b"." + sig.encode()).decode()


def _token_payload(token: str) -> Optional[str]:
    """Проверяет подпись и срок, возвращает строку payload (или None)."""
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        payload, sig = raw.rsplit(b".", 1)
        expected_sig = hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig.decode(), expected_sig):
            return None
        text = payload.decode()
        expires = text.rsplit(":", 1)[-1]
        if time.time() >= int(expires):
            return None
        return text
    except Exception:
        return None


def verify_token(token: str) -> bool:
    """True только для токена владельца (старый формат). Токены сотрудников здесь НЕ проходят:
    так любой старый код, проверяющий токен напрямую, остаётся закрытым для сотрудников."""
    payload = _token_payload(token)
    return payload is not None and ":" not in payload


def token_login(token: str) -> Optional[str]:
    """Логин из токена. None — токен старого формата (владелец до появления ролей)."""
    text = _token_payload(token)
    if text is None or ":" not in text:
        return None
    return text.split(":")[0] or None


def token_fp(token: str) -> str:
    """Отпечаток пароля в токене сотрудника (при смене пароля старые токены перестают работать)."""
    parts = (_token_payload(token) or "").split(":")
    return parts[1] if len(parts) == 3 else ""


def require_admin(authorization: Optional[str] = Header(None)):
    """Dependency для защиты админских эндпоинтов — добавлять как Depends(require_admin)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = current_user(authorization)
    if user is not None and not is_owner(user):
        raise HTTPException(status_code=403, detail="Forbidden")   # сотрудникам — только через require_permission
    return True


# =====================================================
# РОЛИ И ПОЛЬЗОВАТЕЛИ (фундамент, пока нигде не подключён)
# =====================================================
# Владелец ("owner") зашит в коде: все права + управление ролями и пользователями.
# Остальные роли владелец создаёт сам в админке и отмечает права галочками.
# Данные: /data/users.json (список) и /data/roles.json (словарь id -> роль).
# Ни один из этих файлов не создаётся при импорте модуля — только по явному
# вызову из админских эндпоинтов, чтобы тесты и фоновые задачи не писали в /data.
USERS_FILE = os.path.join(DATA_DIR, "users.json")
ROLES_FILE = os.path.join(DATA_DIR, "roles.json")

OWNER_ROLE = "owner"

# Каталог прав: по нему админка будет рисовать галочки при создании роли.
ALL_PERMISSIONS = [
    "today", "today.guest_name", "bookings.view", "guest.contacts", "bookings.edit",
    "bookings.cancel", "dates.block", "payments", "door_code.view", "passports.view",
    "contracts.pdf", "guest.mail", "prices.edit", "site.content", "site.settings",
    "contract.templates", "payment.settings", "calendars.sync", "brand.edit",
    "backup.retention", "monitoring.view",
]

# Только владелец, выдать нельзя никому
OWNER_ONLY = ["admin.users", "admin.roles", "admin.journal", "admin.delete", "admin.checklist"]

PERMISSION_INFO = {
    "today": ("Экран «Сегодня»", "заезды и выезды дня: квартира, время"),
    "today.guest_name": ("Имя гостя в «Сегодня»", "показать имя рядом"),
    "bookings.view": ("Смотреть брони и календарь", "список, карточки, заезды, выезды"),
    "guest.contacts": ("Контакты гостя", "имя, телефон, почта"),
    "bookings.edit": ("Создавать и менять брони", "ручная бронь, правка дат и гостей"),
    "bookings.cancel": ("Отменять брони", "отмена"),
    "dates.block": ("Блокировать даты", "закрыть и открыть даты"),
    "payments": ("Подтверждать оплату, возврат залога", "деньги"),
    "door_code.view": ("Код двери: смотреть", ""),
    "passports.view": ("Паспорта: фото и номер", "в брони"),
    "contracts.pdf": ("Договоры PDF, ссылки подписи", "содержат паспорт"),
    "guest.mail": ("Письма после выезда, промокоды гостям", ""),
    "prices.edit": ("Цены, акции, промокоды", ""),
    "site.content": ("Фото, тексты, отзывы, места, правила, чат", "содержимое сайта"),
    "site.settings": ("Настройки сайта, оформление, каталог, объекты", ""),
    "contract.templates": ("Шаблоны договора и данные для договора", ""),
    "payment.settings": ("Реквизиты оплаты, время автоотмены", ""),
    "calendars.sync": ("Календари площадок", ""),
    "brand.edit": ("Арендодатель и контакты (бренд)", ""),
    "backup.retention": ("Копии, срок хранения данных", ""),
    "monitoring.view": ("Мониторинг", ""),
}

# Заготовки ролей: действуют, пока владелец не сохранил роли сам (roles.json при чтении не создаётся)
DEFAULT_ROLES = {
    "manager": {"name": "Менеджер", "permissions": [
        "today", "today.guest_name", "bookings.view", "guest.contacts", "bookings.edit",
        "dates.block", "payments", "door_code.view"]},
    "maid": {"name": "Горничная", "permissions": ["today"]},
}

_OLD_PERMISSIONS_UNUSED = [
    "dashboard.view",
    "bookings.view", "bookings.create", "bookings.edit",
    "calendar.edit", "prices.edit", "promo.edit",
    "contract.view", "contract.edit", "archive.view",
    "memo.edit", "checklist.edit", "rules.edit",
    "site.view", "site.edit", "photos.edit", "discounts.edit",
    "places.edit", "reviews.edit", "contacts.edit",
    "settings.view", "settings.edit", "properties.edit",
    "catalog.edit", "integrations.edit", "chat.edit", "monitoring.view",
    "admin.roles", "admin.users",
]


def load_users() -> list:
    """Список пользователей (только чтение, файл не создаётся)."""
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_users(users: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def load_roles() -> dict:
    """Словарь ролей (только чтение, файл не создаётся)."""
    try:
        with open(ROLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else copy.deepcopy(DEFAULT_ROLES)
    except Exception:
        return copy.deepcopy(DEFAULT_ROLES)


def save_roles(roles: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(roles, f, ensure_ascii=False, indent=2)


def find_user(login: str) -> Optional[dict]:
    if not login:
        return None
    wanted = str(login).strip().lower()
    for user in load_users():
        if str(user.get("login", "")).strip().lower() == wanted:
            return user
    return None


def ensure_owner_user() -> Optional[dict]:
    """Создаёт владельца из текущего пароля, если users.json ещё нет.

    Вызывается только из админских эндпоинтов (не при импорте и не в тестах).
    Существующий пароль не меняется: берётся готовый хэш из admin_auth.json,
    иначе хэшируется ADMIN_PASSWORD из .env. Нет пароля — ничего не создаётся.
    """
    if os.path.exists(USERS_FILE):
        return None
    stored_hash = ""
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                stored_hash = json.load(f).get("password_hash", "") or ""
        except Exception:
            stored_hash = ""
    if not stored_hash:
        if not ADMIN_PASSWORD:
            return None
        stored_hash = hash_password(ADMIN_PASSWORD)
    owner = {
        "login": "admin",
        "name": "Владелец",
        "role": OWNER_ROLE,
        "password_hash": stored_hash,
        "created_at": int(time.time()),
    }
    save_users([owner])
    return owner


def is_owner(user: Optional[dict]) -> bool:
    # None — сессия старого формата (владелец вошёл до появления ролей)
    return user is None or user.get("role") == OWNER_ROLE


def get_user_permissions(user: Optional[dict]) -> list:
    if is_owner(user):
        return list(ALL_PERMISSIONS) + list(OWNER_ONLY)
    role = load_roles().get((user or {}).get("role", "")) or {}
    perms = role.get("permissions") or []
    return [p for p in perms if p in ALL_PERMISSIONS]


def user_has_permission(user: Optional[dict], permission: str) -> bool:
    return permission in get_user_permissions(user)


def current_user(authorization: Optional[str] = None) -> Optional[dict]:
    """Пользователь по заголовку Authorization. None — владелец (старый токен)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[len("Bearer "):]
    if _token_payload(token) is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    login = token_login(token)
    if login is None:
        return None
    user = find_user(login)
    # удалён или отключён — сессия больше не действует
    if user is None or user.get("active", True) is False:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # сменился пароль — старые токены этого сотрудника недействительны
    if not hmac.compare_digest(token_fp(token), password_fp(user)):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def password_fp(user: dict) -> str:
    """Короткий отпечаток пароля сотрудника (кладётся в токен)."""
    raw = SESSION_SECRET + "|" + str((user or {}).get("password_hash", ""))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def check_staff_login(login: str, password: str) -> Optional[dict]:
    """Сотрудник по логину и паролю (None — неверно или отключён)."""
    user = find_user(login)
    if not user or user.get("active", True) is False:
        verify_password(password or "", "00:00")   # выравниваем время ответа
        return None
    if not verify_password(password or "", user.get("password_hash", "")):
        return None
    return user


def require_permission(permission: str):
    """Использовать как Depends(require_permission("bookings.view"))."""
    def checker(authorization: Optional[str] = Header(None),
                x_property_id: Optional[str] = Header(None, alias="X-Property-Id")):
        user = current_user(authorization)
        if is_owner(user):
            return user
        if not user_has_permission(user, permission):
            raise HTTPException(status_code=403, detail="Forbidden")
        allowed = user.get("properties") or None
        if allowed:
            try:
                pid = int(x_property_id) if x_property_id else 1
            except ValueError:
                raise HTTPException(status_code=400, detail="Неверный номер объекта")
            if pid not in allowed:
                raise HTTPException(status_code=403, detail="Нет доступа к этой квартире")
        return user
    return checker