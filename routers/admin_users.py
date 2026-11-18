"""Управление пользователями и ролями (только для владельца)."""
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from pydantic import BaseModel
from core.auth import (
    current_user, require_permission,
    load_users, save_users, load_roles, save_roles,
    find_user, hash_password, verify_password,
    ALL_PERMISSIONS, OWNER_ROLE
)
import time

router = APIRouter(prefix="/api/admin", tags=["admin"])


# =====================================================
# МОДЕЛИ
# =====================================================

class UserCreate(BaseModel):
    login: str
    password: str
    name: str = ""
    role: str


class UserUpdate(BaseModel):
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class RoleCreate(BaseModel):
    id: str
    name: str
    permissions: list[str]


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[list[str]] = None


# =====================================================
# ПОЛЬЗОВАТЕЛИ
# =====================================================

@router.get("/users")
def get_users(user=Depends(require_permission("admin.users"))):
    """Список пользователей (без паролей)."""
    users = load_users()
    return [
        {
            "login": u.get("login"),
            "name": u.get("name", ""),
            "role": u.get("role"),
            "created_at": u.get("created_at"),
        }
        for u in users
    ]


@router.post("/users")
def create_user(data: UserCreate, user=Depends(require_permission("admin.users"))):
    """Создание пользователя."""
    login = data.login.strip().lower()
    if not login:
        raise HTTPException(status_code=400, detail="Логин не может быть пустым")
    
    if find_user(login):
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    
    roles = load_roles()
    if data.role != OWNER_ROLE and data.role not in roles:
        raise HTTPException(status_code=400, detail="Роль не существует")
    
    new_user = {
        "login": login,
        "name": data.name.strip() or login,
        "role": data.role,
        "password_hash": hash_password(data.password),
        "created_at": int(time.time()),
    }
    
    users = load_users()
    users.append(new_user)
    save_users(users)
    
    return {"ok": True, "login": login}


@router.put("/users/{login}")
def update_user(login: str, data: UserUpdate, user=Depends(require_permission("admin.users"))):
    """Обновление пользователя."""
    login = login.strip().lower()
    users = load_users()
    target = next((u for u in users if u.get("login") == login), None)
    
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if target.get("role") == OWNER_ROLE and data.role and data.role != OWNER_ROLE:
        raise HTTPException(status_code=400, detail="Нельзя понизить владельца")
    
    if data.role and data.role != OWNER_ROLE:
        roles = load_roles()
        if data.role not in roles:
            raise HTTPException(status_code=400, detail="Роль не существует")
    
    if data.name is not None:
        target["name"] = data.name.strip() or target["login"]
    if data.role is not None:
        target["role"] = data.role
    if data.password:
        target["password_hash"] = hash_password(data.password)
    
    save_users(users)
    return {"ok": True}


@router.delete("/users/{login}")
def delete_user(login: str, user=Depends(require_permission("admin.users"))):
    """Удаление пользователя."""
    login = login.strip().lower()
    users = load_users()
    target = next((u for u in users if u.get("login") == login), None)
    
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if target.get("role") == OWNER_ROLE:
        owners = [u for u in users if u.get("role") == OWNER_ROLE]
        if len(owners) == 1:
            raise HTTPException(status_code=400, detail="Нельзя удалить единственного владельца")
    
    users = [u for u in users if u.get("login") != login]
    save_users(users)
    return {"ok": True}


# =====================================================
# РОЛИ
# =====================================================

@router.get("/roles")
def get_roles(user=Depends(require_permission("admin.roles"))):
    """Список ролей."""
    roles = load_roles()
    return [
        {
            "id": role_id,
            "name": role_data.get("name", role_id),
            "permissions": role_data.get("permissions", []),
        }
        for role_id, role_data in roles.items()
    ]


@router.get("/permissions")
def get_all_permissions(user=Depends(require_permission("admin.roles"))):
    """Список всех возможных прав (для галочек в админке)."""
    return ALL_PERMISSIONS


@router.post("/roles")
def create_role(data: RoleCreate, user=Depends(require_permission("admin.roles"))):
    """Создание роли."""
    role_id = data.id.strip().lower()
    if not role_id:
        raise HTTPException(status_code=400, detail="ID роли не может быть пустым")
    
    if role_id == OWNER_ROLE:
        raise HTTPException(status_code=400, detail="Нельзя создать роль 'owner'")
    
    roles = load_roles()
    if role_id in roles:
        raise HTTPException(status_code=400, detail="Роль уже существует")
    
    # Фильтруем права — только из ALL_PERMISSIONS
    valid_perms = [p for p in data.permissions if p in ALL_PERMISSIONS]
    
    roles[role_id] = {
        "name": data.name.strip() or role_id,
        "permissions": valid_perms,
    }
    save_roles(roles)
    return {"ok": True, "id": role_id}


@router.put("/roles/{role_id}")
def update_role(role_id: str, data: RoleUpdate, user=Depends(require_permission("admin.roles"))):
    """Обновление роли."""
    role_id = role_id.strip().lower()
    if role_id == OWNER_ROLE:
        raise HTTPException(status_code=400, detail="Нельзя изменить роль 'owner'")
    
    roles = load_roles()
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    
    if data.name is not None:
        roles[role_id]["name"] = data.name.strip() or role_id
    if data.permissions is not None:
        valid_perms = [p for p in data.permissions if p in ALL_PERMISSIONS]
        roles[role_id]["permissions"] = valid_perms
    
    save_roles(roles)
    return {"ok": True}


@router.delete("/roles/{role_id}")
def delete_role(role_id: str, user=Depends(require_permission("admin.roles"))):
    """Удаление роли."""
    role_id = role_id.strip().lower()
    if role_id == OWNER_ROLE:
        raise HTTPException(status_code=400, detail="Нельзя удалить роль 'owner'")
    
    roles = load_roles()
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    
    # Проверяем, нет ли пользователей с этой ролью
    users = load_users()
    if any(u.get("role") == role_id for u in users):
        raise HTTPException(status_code=400, detail="Есть пользователи с этой ролью")
    
    del roles[role_id]
    save_roles(roles)
    return {"ok": True}