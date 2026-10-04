"""API: вход администратора и смена пароля."""
import json
from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_admin, check_admin_password, make_token, hash_password
from core.constants import AUTH_FILE
from core.models import AdminLogin, ChangePassword

router = APIRouter()


# =====================================================
# API — ADMIN AUTH
# =====================================================

@router.post("/api/admin/login")
async def admin_login(creds: AdminLogin):
    if not check_admin_password(creds.password):
        raise HTTPException(status_code=401, detail="\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043f\u0430\u0440\u043e\u043b\u044c")
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
