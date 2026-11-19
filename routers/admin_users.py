"""API: вход сотрудников, «кто я», сотрудники и роли (управление — только владелец)."""
import re
import secrets
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from core.auth import (
    ALL_PERMISSIONS,
    LOGIN_MAX_FAILS,
    OWNER_ROLE,
    PERMISSION_INFO,
    check_staff_login,
    client_ip,
    current_user,
    find_user,
    get_user_permissions,
    hash_password,
    is_owner,
    load_roles,
    load_users,
    login_retry_after,
    make_token,
    password_fp,
    register_login_failure,
    register_login_success,
    require_permission,
    save_roles,
    save_users,
)
from core.logger import get_logger
from core.properties import list_properties

logger = get_logger(__name__)

router = APIRouter()

_lock = threading.Lock()
LOGIN_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]{2,31}")
ROLE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_\-]{1,29}")


class StaffLogin(BaseModel):
    login: str
    password: str


class UserCreate(BaseModel):
    login: str
    password: str
    name: str = ""
    role: str
    properties: Optional[List[int]] = None   # None или пусто = все квартиры
    active: bool = True


class UserUpdate(BaseModel):
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    properties: Optional[List[int]] = None
    active: Optional[bool] = None


class RoleCreate(BaseModel):
    id: str
    name: str
    permissions: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[List[str]] = None


def _public(u: dict) -> dict:
    return {"login": u.get("login"), "name": u.get("name", ""), "role": u.get("role"),
            "properties": u.get("properties") or None,
            "active": u.get("active", True) is not False,
            "created_at": u.get("created_at")}


def _check_properties(props):
    if not props:
        return None
    ids = {p["id"] for p in list_properties()}
    if any(p not in ids for p in props):
        raise HTTPException(status_code=400, detail="Выбрана несуществующая квартира")
    return sorted(set(props))


def _clean_perms(perms):
    return [p for p in ALL_PERMISSIONS if p in set(perms or [])]


# ---------------------------------------------------------------------------
# Вход сотрудника и «кто я»
# ---------------------------------------------------------------------------

@router.post("/api/admin/staff-login")
async def staff_login(creds: StaffLogin, request: Request = None):
    ip = client_ip(request)
    wait = login_retry_after(ip)
    if wait:
        raise HTTPException(status_code=429,
                            detail=f"Слишком много неверных попыток. Попробуйте через {(wait + 59) // 60} мин.",
                            headers={"Retry-After": str(wait)})
    user = check_staff_login(creds.login, creds.password)
    if not user:
        count = register_login_failure(ip)
        logger.warning("Неверный вход сотрудника: login=%s ip=%s попытка %s из %s",
                       creds.login[:40], ip, count, LOGIN_MAX_FAILS)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    register_login_success(ip)
    return {"token": make_token(user["login"], password_fp(user)), "name": user.get("name", "")}


@router.get("/api/admin/me")
async def me(authorization: Optional[str] = Header(None)):
    """Кто вошёл, его права и квартиры (админка по этому скрывает лишнее)."""
    user = current_user(authorization)
    owner = is_owner(user)
    return {
        "owner": owner,
        "login": "" if owner else user.get("login"),
        "name": "Владелец" if owner else user.get("name", ""),
        "role": OWNER_ROLE if owner else user.get("role"),
        "permissions": get_user_permissions(user),
        "properties": None if owner else (user.get("properties") or None),
    }


# ---------------------------------------------------------------------------
# Сотрудники
# ---------------------------------------------------------------------------

@router.get("/api/admin/users")
async def get_users(_=Depends(require_permission("admin.users"))):
    return {
        "users": [_public(u) for u in load_users()],
        "roles": [{"id": k, "name": v.get("name", k), "permissions": v.get("permissions", [])}
                  for k, v in load_roles().items()],
        "permissions": [{"key": k, "title": PERMISSION_INFO[k][0], "hint": PERMISSION_INFO[k][1]}
                        for k in ALL_PERMISSIONS],
        "properties": [{"id": p["id"], "name": p["name"]} for p in list_properties()],
    }


@router.post("/api/admin/users")
async def create_user(data: UserCreate, _=Depends(require_permission("admin.users"))):
    login = data.login.strip().lower()
    if not LOGIN_RE.fullmatch(login):
        raise HTTPException(status_code=400, detail="Логин: 3–32 символа, латиница, цифры, «.», «_», «-»")
    if len(data.password or "") < 6:
        raise HTTPException(status_code=400, detail="Пароль: минимум 6 символов")
    if data.role not in load_roles():
        raise HTTPException(status_code=400, detail="Роль не существует")
    props = _check_properties(data.properties)
    with _lock:
        users = load_users()
        if any(str(u.get("login", "")).lower() == login for u in users):
            raise HTTPException(status_code=400, detail="Такой логин уже есть")
        user = {"login": login, "name": data.name.strip()[:80] or login, "role": data.role,
                "password_hash": hash_password(data.password), "properties": props,
                "active": bool(data.active), "created_at": int(time.time())}
        users.append(user)
        save_users(users)
    logger.info("Создан сотрудник %s (роль %s)", login, data.role)
    return _public(user)


@router.put("/api/admin/users/{login}")
async def update_user(login: str, data: UserUpdate, _=Depends(require_permission("admin.users"))):
    fields = data.dict(exclude_unset=True)
    login = login.strip().lower()
    with _lock:
        users = load_users()
        target = next((u for u in users if str(u.get("login", "")).lower() == login), None)
        if not target:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if target.get("role") == OWNER_ROLE:
            raise HTTPException(status_code=400, detail="Владелец управляется отдельно")
        if fields.get("role") is not None:
            if fields["role"] not in load_roles():
                raise HTTPException(status_code=400, detail="Роль не существует")
            target["role"] = fields["role"]
        if fields.get("name") is not None:
            target["name"] = fields["name"].strip()[:80] or target["login"]
        if "properties" in fields:
            target["properties"] = _check_properties(fields["properties"])
        if fields.get("active") is not None:
            target["active"] = bool(fields["active"])
        if fields.get("password"):
            if len(fields["password"]) < 6:
                raise HTTPException(status_code=400, detail="Пароль: минимум 6 символов")
            target["password_hash"] = hash_password(fields["password"])   # старые сессии сотрудника оборвутся
        save_users(users)
    return _public(target)


@router.delete("/api/admin/users/{login}")
async def delete_user(login: str, _=Depends(require_permission("admin.users"))):
    login = login.strip().lower()
    with _lock:
        users = load_users()
        target = next((u for u in users if str(u.get("login", "")).lower() == login), None)
        if not target:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        if target.get("role") == OWNER_ROLE:
            raise HTTPException(status_code=400, detail="Владельца удалить нельзя")
        save_users([u for u in users if u is not target])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Роли
# ---------------------------------------------------------------------------

@router.get("/api/admin/roles")
async def get_roles(_=Depends(require_permission("admin.roles"))):
    return [{"id": k, "name": v.get("name", k), "permissions": v.get("permissions", [])}
            for k, v in load_roles().items()]


@router.post("/api/admin/roles")
async def create_role(data: RoleCreate, _=Depends(require_permission("admin.roles"))):
    role_id = data.id.strip().lower()
    if not ROLE_ID_RE.fullmatch(role_id) or role_id == OWNER_ROLE:
        raise HTTPException(status_code=400, detail="Код роли: 2–30 символов, латиница, цифры, «_», «-»")
    name = data.name.strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название роли")
    with _lock:
        roles = load_roles()
        if role_id in roles:
            raise HTTPException(status_code=400, detail="Такая роль уже есть")
        roles[role_id] = {"name": name, "permissions": _clean_perms(data.permissions)}
        save_roles(roles)
    return {"ok": True, "id": role_id}


@router.put("/api/admin/roles/{role_id}")
async def update_role(role_id: str, data: RoleUpdate, _=Depends(require_permission("admin.roles"))):
    role_id = role_id.strip().lower()
    with _lock:
        roles = load_roles()
        if role_id not in roles:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        if data.name is not None:
            roles[role_id]["name"] = data.name.strip()[:60] or role_id
        if data.permissions is not None:
            roles[role_id]["permissions"] = _clean_perms(data.permissions)
        save_roles(roles)
    return {"ok": True}


@router.delete("/api/admin/roles/{role_id}")
async def delete_role(role_id: str, _=Depends(require_permission("admin.roles"))):
    role_id = role_id.strip().lower()
    with _lock:
        roles = load_roles()
        if role_id not in roles:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        if any(u.get("role") == role_id for u in load_users()):
            raise HTTPException(status_code=400, detail="Роль назначена сотрудникам — сначала смените им роль")
        del roles[role_id]
        save_roles(roles)
    return {"ok": True}
