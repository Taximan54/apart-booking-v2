"""Согласие на ПД: данные арендодателя берутся из настроек объекта, {{EMAIL}} остаётся почтой гостя."""
import core.contract_docs as cd

MARK = ("\ue000", "\ue001")


def _plain(text):
    for m in MARK:
        text = text.replace(m, "")
    return text


def _setup(monkeypatch, template, settings):
    monkeypatch.setattr(cd, "load_consent_template", lambda: template)
    monkeypatch.setattr(cd, "load_contract_settings", lambda pid: settings)
    monkeypatch.setattr(cd, "landlord_brand", lambda *a, **k: "Бренд по умолчанию")
    monkeypatch.setattr(cd, "landlord_domain", lambda *a, **k: "example.ru")
    monkeypatch.setattr(cd, "get_landlord_email", lambda *a, **k: "owner@example.ru")
    monkeypatch.setattr(cd, "_property_address", lambda booking: "Адрес из объекта")


BOOKING = {"guest_name": "Иван", "guest_email": "guest@example.com", "username": "GP-1", "property_id": 1}


def test_consent_uses_landlord_data_and_keeps_guest_email(monkeypatch):
    _setup(monkeypatch, "{{АРЕНДОДАТЕЛЬ}}|{{АДРЕС}}|{{САЙТ}}|{{EMAIL_АРЕНДОДАТЕЛЯ}}|{{EMAIL}}",
           {"landlord_name": "ИП Петров", "address": "г. Омск, ул. Мира, 1", "object_kind": "", "inventory": ""})
    assert _plain(cd.generate_consent(BOOKING)) == "ИП Петров|г. Омск, ул. Мира, 1|example.ru|owner@example.ru|guest@example.com"


def test_consent_falls_back_when_object_settings_empty(monkeypatch):
    _setup(monkeypatch, "{{АРЕНДОДАТЕЛЬ}}|{{АДРЕС}}",
           {"landlord_name": "", "address": "", "object_kind": "", "inventory": ""})
    assert _plain(cd.generate_consent(BOOKING)) == "Бренд по умолчанию|Адрес из объекта"


def test_old_template_without_new_placeholders_is_unchanged(monkeypatch):
    _setup(monkeypatch, "Я, {{ФИО}}, отзыв на email citypause@mail.ru. Договор № {{НОМЕР_БРОНИ}}",
           {"landlord_name": "", "address": "", "object_kind": "", "inventory": ""})
    assert _plain(cd.generate_consent(BOOKING)) == "Я, Иван, отзыв на email citypause@mail.ru. Договор № GP-1"
