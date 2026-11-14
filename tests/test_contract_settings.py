"""Данные объекта для договора: арендодатель, вид объекта, адрес, перечень имущества (у каждого объекта свои)."""
import pytest

from core import contract_docs as cd
from core import contract_settings as cs


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CONTRACT_SETTINGS_FILE", str(tmp_path / "contract_settings.json"))
    monkeypatch.setattr(cs, "property_file",
                        lambda base, pid: base if pid == 1 else base.replace(".json", f"_{pid}.json"))
    monkeypatch.setattr(cd, "get_default_deposit", lambda pid: 6000)
    monkeypatch.setattr(cd, "landlord_brand", lambda: "Городская Пауза")
    monkeypatch.setattr(cd, "landlord_address", lambda: "г. Новосибирск, ул. Дачная, д. 5")
    monkeypatch.setattr(cd, "landlord_domain", lambda: "citypause.ru")
    monkeypatch.setattr(cd, "get_landlord_email", lambda: "info@citypause.ru")
    return tmp_path


BOOKING = {"check_in": "2027-01-10", "check_out": "2027-01-12", "nights": 2, "guest_name": "Иванов И. И.",
           "passport": "0000 000000", "guests_count": 2, "total_price": 7000, "username": "GP-TEST01", "property_id": 1}


def test_defaults_when_nothing_saved(env):
    s = cs.load_contract_settings(1)
    assert s == {"landlord_name": "", "object_kind": "", "address": "", "inventory": "", "basis": ""}
    p = cd._contract_placeholders(BOOKING)
    assert p["АРЕНДОДАТЕЛЬ"] == "Городская Пауза"
    assert p["ВИД_ОБЪЕКТА"] == "помещение"
    assert p["АДРЕС"] == "г. Новосибирск, ул. Дачная, д. 5"


def test_save_load_and_values_are_per_property(env):
    cs.save_contract_settings(2, {"landlord_name": " ООО Ромашка ", "object_kind": "дом", "address": "г. Томск, ул. Лесная, 1", "inventory": "Диван\nСтол"})
    s2 = cs.load_contract_settings(2)
    assert s2["landlord_name"] == "ООО Ромашка" and s2["object_kind"] == "дом" and s2["inventory"] == "Диван\nСтол"
    assert cs.load_contract_settings(1)["landlord_name"] == ""   # у основного объекта ничего не изменилось


def test_placeholders_use_saved_settings(env):
    cs.save_contract_settings(1, {"landlord_name": "ИП Петров", "object_kind": "квартира-студия", "address": "г. Омск, ул. Мира, 3", "inventory": ""})
    p = cd._contract_placeholders(BOOKING)
    assert p["АРЕНДОДАТЕЛЬ"] == "ИП Петров"
    assert p["ВИД_ОБЪЕКТА"] == "квартира-студия"
    assert p["АДРЕС"] == "г. Омск, ул. Мира, 3"
    assert p["ADRES"] == "г. Омск, ул. Мира, 3"


def test_inventory_is_inserted_by_lines_without_bold_markers(env):
    cs.save_contract_settings(1, {"inventory": "Диван\nСтол\nЧайник"})
    text = cd.fill_contract_for_booking("Приложение N 1\n{{ИМУЩЕСТВО}}\nКонец", BOOKING)
    assert "Диван\nСтол\nЧайник" in text
    assert cd._AUTO_BOLD_OPEN not in text.split("Диван")[0].split("Приложение N 1")[1]


def test_template_without_new_placeholders_is_unchanged(env):
    cs.save_contract_settings(1, {"landlord_name": "ООО Ромашка", "inventory": "Диван"})
    assert cd.fill_contract_for_booking("Текст без подстановок имущества", BOOKING) == "Текст без подстановок имущества"


def test_public_values_for_site(env):
    cs.save_contract_settings(1, {"object_kind": "дом"})
    v = cd.contract_public_values(1)
    assert v["object_kind"] == "дом" and v["landlord"] == "Городская Пауза" and v["deposit"] == 6000


def test_too_long_values_are_cut(env):
    saved = cs.save_contract_settings(1, {"landlord_name": "я" * 500})
    assert len(saved["landlord_name"]) == 200


def test_basis_placeholder_default_and_saved(env):
    """Основание права распоряжения (п. 1.3): по умолчанию нейтральный текст, иначе то, что заполнено у объекта."""
    assert cd._contract_placeholders(BOOKING)["ОСНОВАНИЕ"] == "правоустанавливающие документы"
    assert cd.contract_public_values(1)["basis"] == "правоустанавливающие документы"
    cs.save_contract_settings(1, {"basis": "Договор доверительного управления"})
    assert cd._contract_placeholders(BOOKING)["ОСНОВАНИЕ"] == "Договор доверительного управления"
    assert cd.contract_public_values(1)["basis"] == "Договор доверительного управления"
    assert cd.fill_contract_for_booking("п. 1.3: {{ОСНОВАНИЕ}}.", BOOKING).count("Договор доверительного управления") == 1
