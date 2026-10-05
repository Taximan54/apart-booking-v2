"""Данные арендодателя: значения по умолчанию, свои значения, подстановка в договор, API."""
import json

import pytest

def plain(text):
    """Убирает служебные метки автоматического жирного шрифта вокруг подставленных значений."""
    return text.replace("\ue000", "").replace("\ue001", "")


BOOKING = {
    "username": "REF1", "id": 1, "guest_name": "Иванов Иван", "passport": "1234 567890",
    "check_in": "2026-10-10", "check_out": "2026-10-12", "nights": 2, "total_price": 9000,
}


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Подменяет файлы настроек на временные, боевые данные не затрагиваются."""
    import core.landlord as ll
    landlord_file = tmp_path / "landlord.json"
    contacts_file = tmp_path / "contacts.json"
    import routers.content as rc
    monkeypatch.setattr(ll, "LANDLORD_FILE", str(landlord_file))
    monkeypatch.setattr(ll, "CONTACTS_FILE", str(contacts_file))
    monkeypatch.setattr(rc, "LANDLORD_FILE", str(landlord_file))   # эндпоинт пишет сюда — не в боевой файл
    return landlord_file, contacts_file


def test_clean_domain():
    from core.landlord import clean_domain
    assert clean_domain("https://www.Example.ru/") == "example.ru"
    assert clean_domain("  HTTP://site.com/path?x=1 ") == "site.com"
    assert clean_domain("") == ""


def test_defaults_when_nothing_saved(files):
    from core.constants import DEFAULT_LANDLORD
    from core.landlord import get_landlord, site_url
    assert get_landlord() == DEFAULT_LANDLORD
    assert site_url() == "https://" + DEFAULT_LANDLORD["domain"]


def test_saved_values_override_and_empty_fields_fall_back(files):
    from core.constants import DEFAULT_LANDLORD
    from core.landlord import get_landlord, landlord_brand, landlord_domain
    landlord_file, _ = files
    landlord_file.write_text(json.dumps({"brand_name": "Тест Бренд", "domain": "HTTPS://Test.RU/", "address": ""}), encoding="utf-8")
    data = get_landlord()
    assert data["brand_name"] == "Тест Бренд"
    assert data["domain"] == "test.ru"
    assert data["address"] == DEFAULT_LANDLORD["address"]   # пустое поле -> по умолчанию
    assert landlord_brand() == "Тест Бренд" and landlord_domain() == "test.ru"


def test_broken_file_does_not_break_anything(files):
    from core.constants import DEFAULT_LANDLORD
    from core.landlord import get_landlord
    landlord_file, _ = files
    landlord_file.write_text("{не json", encoding="utf-8")
    assert get_landlord() == DEFAULT_LANDLORD


def test_email_comes_from_contacts_else_fallback(files):
    from core.constants import LANDLORD_EMAIL
    from core.landlord import get_landlord_email
    _, contacts_file = files
    assert get_landlord_email() == LANDLORD_EMAIL
    contacts_file.write_text(json.dumps({"email": " owner@test.ru "}), encoding="utf-8")
    assert get_landlord_email() == "owner@test.ru"


def test_contract_placeholders_use_settings(files, monkeypatch):
    import core.contract_docs as cd
    landlord_file, contacts_file = files
    landlord_file.write_text(json.dumps({"brand_name": "Тест Бренд", "domain": "test.ru", "address": "г. Омск, ул. Мира, д. 1"}), encoding="utf-8")
    contacts_file.write_text(json.dumps({"email": "owner@test.ru"}), encoding="utf-8")
    monkeypatch.setattr(cd, "load_contract_template", lambda: "{{АРЕНДОДАТЕЛЬ}}|{{АДРЕС}}|{{EMAIL}}|{{САЙТ}}")
    text = cd.generate_contract(dict(BOOKING))
    assert plain(text) == "Тест Бренд|г. Омск, ул. Мира, д. 1|owner@test.ru|test.ru"


def test_contract_uses_current_defaults_when_nothing_saved(files, monkeypatch):
    """Без своих настроек договор выглядит как раньше (адрес, домен, бренд)."""
    import core.contract_docs as cd
    monkeypatch.setattr(cd, "load_contract_template", lambda: "{{АРЕНДОДАТЕЛЬ}}|{{АДРЕС}}|{{САЙТ}}")
    assert plain(cd.generate_contract(dict(BOOKING))) == "Городская Пауза|г. Новосибирск, ул. Дачная, д. 5, квартира 286, 22 этаж|citypause.ru"


def test_api_requires_admin():
    """Оба адреса защищены проверкой администратора."""
    import inspect
    from core.auth import require_admin
    from routers.content import get_landlord_settings, set_landlord_settings
    for func in (get_landlord_settings, set_landlord_settings):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"


def test_api_validates_and_saves(files):
    """Проверка данных и сохранение (обработчики вызываются напрямую, без HTTP-клиента)."""
    import asyncio

    from fastapi import HTTPException

    from core.models import LandlordSettings
    from routers.content import get_landlord_settings, set_landlord_settings

    def save(**kw):
        return asyncio.run(set_landlord_settings(LandlordSettings(**kw), True))

    with pytest.raises(HTTPException) as e1:
        save(brand_name="", domain="не домен", address="")
    assert e1.value.status_code == 400
    with pytest.raises(HTTPException) as e2:
        save(brand_name="x" * 81, domain="", address="")
    assert e2.value.status_code == 400
    with pytest.raises(HTTPException) as e3:
        save(brand_name="", domain="", address="y" * 201)
    assert e3.value.status_code == 400

    ok = save(brand_name=" Мой Дом ", domain="https://www.Moy-Dom.ru/", address="г. Томск, ул. Ленина, 1")
    assert ok == {"brand_name": "Мой Дом", "domain": "moy-dom.ru", "address": "г. Томск, ул. Ленина, 1"}
    assert asyncio.run(get_landlord_settings(True))["domain"] == "moy-dom.ru"


def test_signed_pdf_header_uses_brand(files, monkeypatch, tmp_path):
    """Заголовок подписанного PDF берёт название из настроек, а не из кода."""
    import core.signing as sg
    landlord_file, _ = files
    landlord_file.write_text(json.dumps({"brand_name": "Тест Бренд"}), encoding="utf-8")
    seen = {}
    def fake_pdf(text, ref, extra_blocks=None, header_text=None, **kw):
        seen["header"] = header_text
        seen["text"] = text
        return str(tmp_path / "x.pdf")
    monkeypatch.setattr(sg, "generate_contract_pdf", fake_pdf)
    monkeypatch.setattr(sg, "_passport_photos_with_grid", lambda ref: [])
    booking = dict(BOOKING, guest_phone="+79990000000", guest_email="a@b.c", signed_at="2026-10-04 12:00:00",
                   sign_ip="1.1.1.1", status="confirmed")
    sg.generate_signed_contract_pdf(booking)
    assert seen["header"].startswith("Тест Бренд ")
