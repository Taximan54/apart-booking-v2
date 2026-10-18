"""API: вход администратора и смена пароля."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request

from core.auth import (
    LOGIN_MAX_FAILS,
    check_admin_password,
    client_ip,
    hash_password,
    login_retry_after,
    make_token,
    register_login_failure,
    register_login_success,
    require_admin,
)
from core.constants import AUTH_FILE
from core.logger import get_logger
from core.models import AdminLogin, ChangePassword

logger = get_logger(__name__)

router = APIRouter()


# =====================================================
# API — ADMIN AUTH
# =====================================================

@router.post("/api/admin/login")
async def admin_login(creds: AdminLogin, request: Request = None):
    ip = client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        logger.warning("Вход в админку заблокирован (много неверных паролей): ip=%s, ещё %s сек", ip, wait)
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много неверных попыток. Попробуйте через {(wait + 59) // 60} мин.",
            headers={"Retry-After": str(wait)},
        )
    if not check_admin_password(creds.password):
        count = register_login_failure(ip)
        logger.warning("Неверный пароль при входе в админку: ip=%s, попытка %s из %s", ip, count, LOGIN_MAX_FAILS)
        raise HTTPException(status_code=401, detail="Неверный пароль")
    register_login_success(ip)
    return {"token": make_token()}

@router.post("/api/admin/change-password")
async def change_password(cp: ChangePassword, _: bool = Depends(require_admin)):
    if not check_admin_password(cp.old_password):
        raise HTTPException(status_code=401, detail="\u0421\u0442\u0430\u0440\u044b\u0439 \u043f\u0430\u0440\u043e\u043b\u044c \u0432\u0432\u0435\u0434\u0451\u043d \u043d\u0435\u0432\u0435\u0440\u043d\u043e")
    if len(cp.new_password) < 4:
        raise HTTPException(status_code=400, detail="\u041c\u0438\u043d\u0438\u043c\u0443\u043c 4 \u0441\u0438\u043c\u0432\u043e\u043b\u0430")
    with open(AUTH_FILE, "w") as f:
        json.dump({"password_hash": hash_password(cp.new_password)}, f)
    return {"ok": True}
