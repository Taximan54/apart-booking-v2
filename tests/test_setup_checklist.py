"""Чек-лист «Что осталось заполнить»: читает данные, ничего не меняет, боевой /data не трогает."""
import json

import pytest

import core.setup_checklist as sc


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Пустая установка: всё подменено временными файлами."""
    monkeypatch.setattr(sc, "CONTACTS_FILE", str(tmp_path / "contacts.json"))
    monkeypatch.setattr(sc, "PAYMENT_FILE", str(tmp_path / "payment.json"))
    monkeypatch.setattr(sc, "PAYMENT_QR_PATH", str(tmp_path / "qr.png"))
    monkeypatch.setattr(sc, "PRICE_FILE", str(tmp_path / "prices.json"))
    monkeypatch.setattr(sc, "get_landlord", lambda: {"brand_name": "Моя квартира", "domain": "example.ru", "address": "адрес не указан"})
    monkeypatch.setattr(sc, "get_site_settings_dict", lambda pid=1: {"site_name": "Моя квартира", "location_address": ""})
    monkeypatch.setattr(sc, "load_contract_settings", lambda pid: {"landlord_name": "", "address": ""})
    monkeypatch.setattr(sc, "_photos_count", lambda pid: 0)
    monkeypatch.setattr(sc.mailer, "MAIL_FROM", "")
    monkeypatch.setattr(sc.mailer, "MAIL_PASSWORD", "")
    monkeypatch.setattr(sc.config, "BASE_URL", "")
    monkeypatch.setattr(sc, "get_backup_password", lambda: "")
    monkeypatch.delenv("NOINDEX", raising=False)
    return tmp_path, monkeypatch


def _done(result):
    return {i["key"]: i["done"] for i in result["items"]}


def fill_everything(tmp_path, mp):
    (tmp_path / "contacts.json").write_text(json.dumps({"email": "a@b.ru", "phone": "+7 999"}), encoding="utf-8")
    (tmp_path / "payment.json").write_text(json.dumps({"sbp_link": "https://pay", "sbp_phone": ""}), encoding="utf-8")
    (tmp_path / "prices.json").write_text("{}", encoding="utf-8")
    mp.setattr(sc, "get_landlord", lambda: {"brand_name": "Дом", "domain": "dom.ru", "address": "г. Н., ул. А., 1"})
    mp.setattr(sc, "get_site_settings_dict", lambda pid=1: {"site_name": "Дом у Оперного", "location_address": "ул. А., 1"})
    mp.setattr(sc, "load_contract_settings", lambda pid: {"landlord_name": "ИП Иванов", "address": "ул. А., 1"})
    mp.setattr(sc, "_photos_count", lambda pid: 3)
    mp.setattr(sc.mailer, "MAIL_FROM", "x@mail.ru")
    mp.setattr(sc.mailer, "MAIL_PASSWORD", "pw")
    mp.setattr(sc.config, "BASE_URL", "https://dom.ru")
    mp.setattr(sc, "get_backup_password", lambda: "secret")


def test_empty_install_has_everything_undone(env):
    result = sc.build_checklist(1)
    assert result["complete"] is False and result["total"] == len(result["items"])
    # NOINDEX не задан, значит сайт открыт для поисковиков: этот пункт готов
    done = _done(result)
    assert done.pop("indexing") is True
    assert not any(done.values())
    assert result["done"] == 1


def test_everything_filled_is_complete(env):
    tmp_path, mp = env
    fill_everything(tmp_path, mp)
    result = sc.build_checklist(1)
    assert result["complete"] is True and result["done"] == result["total"]


def test_placeholder_brand_is_not_done(env):
    tmp_path, mp = env
    fill_everything(tmp_path, mp)
    mp.setattr(sc, "get_landlord", lambda: {"brand_name": "Моя квартира", "domain": "dom.ru", "address": "г. Н., ул. А., 1"})
    assert _done(sc.build_checklist(1))["landlord"] is False
    mp.setattr(sc, "get_site_settings_dict", lambda pid=1: {"site_name": "Моя квартира", "location_address": "x"})
    assert _done(sc.build_checklist(1))["site_name"] is False


def test_contacts_need_email_and_one_more_way(env):
    tmp_path, mp = env
    (tmp_path / "contacts.json").write_text(json.dumps({"email": "a@b.ru"}), encoding="utf-8")
    assert _done(sc.build_checklist(1))["contacts"] is False
    (tmp_path / "contacts.json").write_text(json.dumps({"phone": "+7 999"}), encoding="utf-8")
    assert _done(sc.build_checklist(1))["contacts"] is False
    (tmp_path / "contacts.json").write_text(json.dumps({"email": "a@b.ru", "telegram": "@x"}), encoding="utf-8")
    assert _done(sc.build_checklist(1))["contacts"] is True


def test_payment_accepts_link_phone_or_qr(env):
    tmp_path, mp = env
    assert _done(sc.build_checklist(1))["payment"] is False
    (tmp_path / "payment.json").write_text(json.dumps({"sbp_phone": "+7 999"}), encoding="utf-8")
    assert _done(sc.build_checklist(1))["payment"] is True
    (tmp_path / "payment.json").write_text("{}", encoding="utf-8")
    (tmp_path / "qr.png").write_bytes(b"png")
    assert _done(sc.build_checklist(1))["payment"] is True


def test_noindex_makes_indexing_item_undone(env):
    tmp_path, mp = env
    fill_everything(tmp_path, mp)
    mp.setenv("NOINDEX", "1")
    result = sc.build_checklist(1)
    assert _done(result)["indexing"] is False and result["complete"] is False


def test_server_items_are_marked_and_have_hint(env):
    result = sc.build_checklist(1)
    server = {i["key"]: i for i in result["items"] if i["server"]}
    assert set(server) == {"mail", "base_url", "backup_password", "indexing"}
    assert all(i["hint"] for i in server.values())


def test_photo_count_error_means_not_done(env):
    tmp_path, mp = env
    def boom(pid):
        raise RuntimeError("нет папки")
    mp.setattr(sc, "_photos_count", boom)
    assert _done(sc.build_checklist(1))["photos"] is False


def test_checklist_never_writes_files(env):
    tmp_path, mp = env
    before = sorted(p.name for p in tmp_path.iterdir())
    sc.build_checklist(1)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_api_requires_admin_and_returns_items(env):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.auth import require_admin
    from core.properties import admin_property_id
    from routers.setup import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/admin/setup-checklist").status_code in (401, 403)
    app.dependency_overrides[require_admin] = lambda: True
    app.dependency_overrides[admin_property_id] = lambda: 1
    r = client.get("/api/admin/setup-checklist")
    assert r.status_code == 200 and r.json()["total"] == len(r.json()["items"])
