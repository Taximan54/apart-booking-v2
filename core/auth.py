"""Авторизация администратора (пароль, токены сессии)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from fastapi import Header, HTTPException
from typing import Optional

from core.constants import AUTH_FILE


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

def make_token() -> str:
    expires = int(time.time()) + SESSION_TTL
    payload = str(expires).encode()
    sig = hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload + b"." + sig.encode()).decode()

def verify_token(token: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        payload, sig = raw.rsplit(b".", 1)
        expected_sig = hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig.decode(), expected_sig):
            return False
        return time.time() < int(payload.decode())
    except Exception:
        return False

def require_admin(authorization: Optional[str] = Header(None)):
    """Dependency для защиты админских эндпоинтов — добавлять как Depends(require_admin)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not verify_token(authorization[len("Bearer "):]):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True
