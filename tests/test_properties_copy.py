"""Копирование настроек из основного объекта при создании нового."""
import json
import os

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    import core.properties as props
    data = tmp_path / "data"
    data.mkdir()
    legacy = {name: str(data / name) for name in (
        "prices.json", "description.txt", "house_rules.txt", "checkin_memo.txt", "checkout_checklist.txt",
        "settings.json", "places.json", "discounts.json")}
    monkeypatch.setattr(props, "COPYABLE_FILES", tuple(legacy.values()))
    monkeypatch.setattr(props, "PROPERTIES_DIR", str(data / "properties"))
    return props, legacy


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_copies_settings_and_removes_photos(env):
    props, legacy = env
    _write(legacy["prices.json"], {"weekday": 3000, "weekend": 4000, "deposit": 6000})
    _write(legacy["description.txt"], "Уютная студия")
    _write(legacy["house_rules.txt"], "Не курить")
    _write(legacy["checkin_memo.txt"], "Памятка заезда")
    _write(legacy["checkout_checklist.txt"], "Чек-лист выезда")
    _write(legacy["settings.json"], {"site_name": "Городская Пауза", "hero_photo": "a.jpg", "hero_photo_mobile": "b.jpg",
                                     "map_photo": "c.jpg", "map_url": "https://maps.example/1", "hero_title": "Заголовок"})
    _write(legacy["places.json"], [{"id": "1", "name": "Парк", "photo": "park.jpg", "description": "рядом"}])
    _write(legacy["discounts.json"], [{"id": "2", "name": "Акция", "photo": "d.jpg", "photo_mobile": "dm.jpg"}])
    before = {k: open(p, encoding="utf-8").read() for k, p in legacy.items()}

    copied = props.copy_property_settings(1, 5)

    assert sorted(copied) == sorted(os.path.basename(p) for p in legacy.values())
    target = lambda name: props.property_file(legacy[name], 5)
    assert _read_json(target("prices.json")) == {"weekday": 3000, "weekend": 4000, "deposit": 6000}
    assert open(target("description.txt"), encoding="utf-8").read() == "Уютная студия"
    assert open(target("checkout_checklist.txt"), encoding="utf-8").read() == "Чек-лист выезда"
    settings = _read_json(target("settings.json"))
    assert settings["site_name"] == "Городская Пауза" and settings["hero_title"] == "Заголовок"
    assert settings["hero_photo"] == settings["hero_photo_mobile"] == settings["map_photo"] == settings["map_url"] == ""
    assert _read_json(target("places.json")) == [{"id": "1", "name": "Парк", "photo": "", "description": "рядом"}]
    assert _read_json(target("discounts.json")) == [{"id": "2", "name": "Акция", "photo": "", "photo_mobile": ""}]
    # основной объект не изменился
    assert {k: open(p, encoding="utf-8").read() for k, p in legacy.items()} == before


def test_missing_and_broken_files_do_not_break_copy(env):
    props, legacy = env
    _write(legacy["description.txt"], "Текст")
    _write(legacy["prices.json"], "{не json")                                           # битый файл пропускается
    copied = props.copy_property_settings(1, 7)
    assert copied == ["description.txt"]
    assert open(props.property_file(legacy["description.txt"], 7), encoding="utf-8").read() == "Текст"


def test_copy_to_itself_does_nothing(env):
    props, legacy = env
    _write(legacy["description.txt"], "Текст")
    assert props.copy_property_settings(1, 1) == []


def test_create_property_model_defaults_to_no_copy():
    from core.models import PropertyCreate
    assert PropertyCreate(name="Квартира").copy_settings is False
    assert PropertyCreate(name="Квартира", copy_settings=True).copy_settings is True
