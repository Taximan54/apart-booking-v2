"""Защита входа в админку от подбора пароля: после 5 неверных паролей подряд — блокировка на 15 минут."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_state():
    import core.auth as auth
    auth._login_fails.clear()
    yield
    auth._login_fails.clear()


def fake_request(ip):
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers={})


def test_blocks_after_five_failures_and_unblocks_later():
    import core.auth as a
    t = 1000.0
    for i in range(4):
        assert a.register_login_failure("1.1.1.1", t + i) == i + 1
        assert a.login_retry_after("1.1.1.1", t + i) == 0
    assert a.register_login_failure("1.1.1.1", t + 4) == 5
    wait = a.login_retry_after("1.1.1.1", t + 5)
    assert 0 < wait <= a.LOGIN_LOCK_SECONDS
    assert a.login_retry_after("2.2.2.2", t + 5) == 0                                    # другой адрес не затронут
    assert a.login_retry_after("1.1.1.1", t + 4 + a.LOGIN_LOCK_SECONDS) == 0             # через 15 минут блокировка снята
    assert a.register_login_failure("1.1.1.1", t + 4 + a.LOGIN_LOCK_SECONDS) == 1        # и счёт начинается заново


def test_success_resets_counter():
    import core.auth as a
    for i in range(4):
        a.register_login_failure("1.1.1.1", 1000.0 + i)
    a.register_login_success("1.1.1.1")
    assert a.register_login_failure("1.1.1.1", 1010.0) == 1


def test_login_handler_blocks_even_correct_password(monkeypatch):
    from core.models import AdminLogin
    from routers import admin_auth as m
    monkeypatch.setattr(m, "check_admin_password", lambda p: p == "ok")
    req = fake_request("3.3.3.3")
    for _ in range(5):
        with pytest.raises(HTTPException) as e:
            run(m.admin_login(AdminLogin(password="wrong"), req))
        assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:                                               # 6-я попытка — блок, даже с верным паролем
        run(m.admin_login(AdminLogin(password="ok"), req))
    assert e.value.status_code == 429 and "Retry-After" in e.value.headers
    assert "token" in run(m.admin_login(AdminLogin(password="ok"), fake_request("4.4.4.4")))   # другой адрес входит как обычно


def test_login_handler_correct_password_still_works_and_resets(monkeypatch):
    from core.models import AdminLogin
    from routers import admin_auth as m
    monkeypatch.setattr(m, "check_admin_password", lambda p: p == "ok")
    req = fake_request("5.5.5.5")
    for _ in range(4):
        with pytest.raises(HTTPException):
            run(m.admin_login(AdminLogin(password="wrong"), req))
    assert "token" in run(m.admin_login(AdminLogin(password="ok"), req))
    for _ in range(4):                                                                    # счётчик обнулился после успешного входа
        with pytest.raises(HTTPException) as e:
            run(m.admin_login(AdminLogin(password="wrong"), req))
        assert e.value.status_code == 401


def test_direct_call_without_request_is_not_limited(monkeypatch):
    from core.models import AdminLogin
    from routers import admin_auth as m
    monkeypatch.setattr(m, "check_admin_password", lambda p: p == "ok")
    for _ in range(10):
        with pytest.raises(HTTPException) as e:
            run(m.admin_login(AdminLogin(password="wrong")))
        assert e.value.status_code == 401
    assert "token" in run(m.admin_login(AdminLogin(password="ok")))
