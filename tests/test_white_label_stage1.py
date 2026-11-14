"""Белая этикетка, этап 1: в шаблонах и страницах нет данных владельца, а поле «Основание права распоряжения» работает."""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("rel", ["static/contract_template.txt", "static/consent_template.txt"])
def test_static_templates_have_no_owner_data(rel):
    text = _read(rel)
    for bad in ("Дачная", "citypause", "Городская Пауза", "Икеа", "кв.286", "Новосибирск"):
        assert bad not in text, f"{rel}: осталось «{bad}»"


def test_contract_template_uses_placeholders():
    text = _read("static/contract_template.txt")
    for key in ("{{АРЕНДОДАТЕЛЬ}}", "{{ВИД_ОБЪЕКТА}}", "{{АДРЕС}}", "{{ОСНОВАНИЕ}}", "{{ИМУЩЕСТВО}}",
                "{{ФИО}}", "{{ДАТА_ДОГОВОРА}}", "{{НОЧЕЙ}}", "{{ИТОГО}}", "Приложение N 1", "Приложение N 2"):
        assert key in text, f"в шаблоне договора нет {key}"


def test_consent_template_uses_landlord_email():
    assert "{{EMAIL_АРЕНДОДАТЕЛЯ}}" in _read("static/consent_template.txt")


@pytest.mark.parametrize("rel,bad", [
    ("static/index.html", "BASE: 'https://citypause.ru'"),
    ("static/discounts.html", "const API_BASE = 'https://citypause.ru'"),
    ("static/admin-js/core.js", "|| 'https://citypause.ru';"),
])
def test_pages_do_not_hardcode_site_address(rel, bad):
    assert bad not in _read(rel)


def test_contract_settings_basis_roundtrip(tmp_path, monkeypatch):
    from core import contract_settings as cs
    monkeypatch.setattr(cs, "property_file", lambda legacy, pid=1: str(tmp_path / f"cs_{pid}.json"))
    assert cs.load_contract_settings(1)["basis"] == ""
    saved = cs.save_contract_settings(1, {"basis": "  Свидетельство о праве собственности  ", "address": "x"})
    assert saved["basis"] == "Свидетельство о праве собственности"
    assert cs.load_contract_settings(1)["basis"] == "Свидетельство о праве собственности"
    assert len(cs.save_contract_settings(2, {"basis": "я" * 900})["basis"]) == 500
    assert cs.load_contract_settings(3)["basis"] == ""   # у другого объекта своё значение
