"""Проверки ролей: токены, права, квартиры, отключение. Без сети и без записи в /data."""
import pytest
from fastapi import HTTPException

from core import auth


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(auth, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(auth, "ROLES_FILE", str(tmp_path / "roles.json"))
    monkeypatch.setattr(auth, "SESSION_SECRET", "test-secret")
    auth.save_users([
        {"login": "anna", "name": "Анна", "role": "maid", "password_hash": auth.hash_password("secret1"),
         "properties": [2], "active": True},
        {"login": "petr", "name": "Пётр", "role": "manager", "password_hash": auth.hash_password("secret2"),
         "properties": None, "active": True},
        {"login": "off", "name": "Off", "role": "manager", "password_hash": auth.hash_password("secret3"),
         "properties": None, "active": False},
    ])


def staff_header(login):
    user = auth.find_user(login)
    return "Bearer " + auth.make_token(login, auth.password_fp(user))


def owner_header():
    return "Bearer " + auth.make_token()


def test_owner_old_token_passes_everything():
    assert auth.require_admin(owner_header()) is True
    assert auth.require_permission("passports.view")(owner_header(), None) is None
    assert auth.require_permission("admin.users")(owner_header(), None) is None


def test_garbage_and_missing_token_rejected():
    for bad in (None, "", "Bearer abc", "Token x"):
        with pytest.raises(HTTPException) as e:
            auth.require_admin(bad)
        assert e.value.status_code == 401


def test_staff_token_cannot_use_owner_only_endpoints():
    with pytest.raises(HTTPException) as e:
        auth.require_admin(staff_header("petr"))
    assert e.value.status_code == 403


def test_default_roles_match_table():
    manager = set(auth.get_user_permissions(auth.find_user("petr")))
    assert {"today", "bookings.view", "guest.contacts", "bookings.edit", "dates.block",
            "payments", "door_code.view"} <= manager
    for forbidden in ("bookings.cancel", "passports.view", "prices.edit", "admin.users", "contracts.pdf"):
        assert forbidden not in manager
    assert auth.get_user_permissions(auth.find_user("anna")) == ["today"]


def test_permission_check():
    ok = auth.require_permission("bookings.view")
    assert ok(staff_header("petr"), None)["login"] == "petr"
    with pytest.raises(HTTPException) as e:
        ok(staff_header("anna"), "2")
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        auth.require_permission("admin.users")(staff_header("petr"), None)


def test_property_restriction():
    check = auth.require_permission("today")
    assert check(staff_header("anna"), "2")["login"] == "anna"
    with pytest.raises(HTTPException) as e:
        check(staff_header("anna"), "1")
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        check(staff_header("anna"), None)       # без заголовка = объект 1
    assert check(staff_header("petr"), "5")     # без ограничения — любая


def test_inactive_and_deleted_user_rejected():
    header = staff_header("off")
    with pytest.raises(HTTPException) as e:
        auth.current_user(header)
    assert e.value.status_code == 401
    header = staff_header("petr")
    auth.save_users([u for u in auth.load_users() if u["login"] != "petr"])
    with pytest.raises(HTTPException):
        auth.current_user(header)


def test_password_change_kills_old_session():
    header = staff_header("petr")
    assert auth.current_user(header)["login"] == "petr"
    users = auth.load_users()
    for u in users:
        if u["login"] == "petr":
            u["password_hash"] = auth.hash_password("newpass1")
    auth.save_users(users)
    with pytest.raises(HTTPException):
        auth.current_user(header)


def test_staff_login_checks():
    assert auth.check_staff_login("PETR", "secret2")["login"] == "petr"
    assert auth.check_staff_login("petr", "wrong") is None
    assert auth.check_staff_login("off", "secret3") is None
    assert auth.check_staff_login("nobody", "x") is None


def test_missing_files_do_not_break_and_are_not_created(tmp_path):
    (tmp_path / "users.json").unlink()
    assert auth.load_users() == []
    assert not (tmp_path / "roles.json").exists()
    assert "manager" in auth.load_roles()
    assert not (tmp_path / "roles.json").exists()
