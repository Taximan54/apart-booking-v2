"""Общие функции, вынесенные из дублей: поиск брони, загрузка фото паспорта, значения по умолчанию."""
import asyncio
import io
import sqlite3

import pytest
from PIL import Image


def _jpeg(size=(1200, 1600)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 190, 180)).save(buf, format="JPEG")
    return buf.getvalue()


class FakeUpload:
    """Минимальная замена UploadFile для проверки без HTTP."""
    def __init__(self, data, filename="p.jpg"):
        self._data, self.filename = data, filename

    async def read(self):
        return self._data


def test_booking_ref_alt():
    from core.db import booking_ref_alt
    assert booking_ref_alt("GP-ABC123") == "\u0413\u041f-ABC123"
    assert booking_ref_alt("OTHER") == "OTHER"
    assert booking_ref_alt("") == ""


def test_find_booking_row_by_ref_alt_and_id():
    from core.db import find_booking_row
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE bookings (id INTEGER PRIMARY KEY, username TEXT, guest_name TEXT)")
    conn.execute("INSERT INTO bookings (id, username, guest_name) VALUES (7, 'GP-AAA111', 'Иван')")
    conn.execute("INSERT INTO bookings (id, username, guest_name) VALUES (8, '\u0413\u041f-BBB222', 'Пётр')")
    assert find_booking_row(conn, "GP-AAA111")["guest_name"] == "Иван"
    assert find_booking_row(conn, "GP-BBB222")["guest_name"] == "Пётр"      # старая запись с «ГП-»
    assert find_booking_row(conn, "7")["username"] == "GP-AAA111"           # по id
    assert find_booking_row(conn, "GP-NOPE") is None
    assert find_booking_row(conn, "GP-AAA111", "guest_name")["guest_name"] == "Иван"


@pytest.fixture
def passport_dirs(tmp_path, monkeypatch):
    import core.passports as pp
    pdir = tmp_path / "passports"
    map_file = tmp_path / "map.json"
    monkeypatch.setattr(pp, "PASSPORT_DIR", str(pdir))
    monkeypatch.setattr(pp, "PASSPORT_MAP_FILE", str(map_file))
    return pdir, map_file


def test_save_uploaded_passport_photo(passport_dirs):
    from core.passports import save_uploaded_passport_photo
    pdir, _ = passport_dirs
    filename, size = asyncio.run(save_uploaded_passport_photo(FakeUpload(_jpeg())))
    assert filename.startswith("passport_") and filename.endswith(".jpg")
    assert (pdir / filename).exists() and (pdir / filename).stat().st_size == size
    with Image.open(pdir / filename) as im:
        assert max(im.size) <= 1600     # сжато до 1600 px по длинной стороне


def test_save_uploaded_passport_photo_rejects_bad_files(passport_dirs):
    from fastapi import HTTPException
    from core.passports import save_uploaded_passport_photo
    with pytest.raises(HTTPException) as e1:
        asyncio.run(save_uploaded_passport_photo(FakeUpload(b"not an image")))
    assert e1.value.status_code == 400 and "изображение" in e1.value.detail
    with pytest.raises(HTTPException) as e2:
        asyncio.run(save_uploaded_passport_photo(FakeUpload(b"0" * (20 * 1024 * 1024 + 1))))
    assert e2.value.status_code == 400 and "большой" in e2.value.detail


def test_set_passport_slot_keeps_other_slot(passport_dirs):
    from core.passports import load_passport_map, set_passport_slot
    set_passport_slot("GP-AAA111", "main", "a.jpg")
    set_passport_slot("GP-AAA111", "reg1", "b.jpg")
    set_passport_slot("GP-AAA111", "main", "c.jpg")     # замена первого фото не трогает второе
    assert load_passport_map()["GP-AAA111"] == {"main": "c.jpg", "reg1": "b.jpg"}


def test_site_settings_model_matches_default_settings():
    """Значения по умолчанию в модели и в константах не должны расходиться."""
    from core.constants import DEFAULT_SETTINGS
    from core.models import SiteSettings
    model = SiteSettings().model_dump()
    assert set(model) == set(DEFAULT_SETTINGS)
    for key, value in DEFAULT_SETTINGS.items():
        assert model[key] == value, f"расхождение в поле {key}"


def test_site_settings_defaults_are_independent_copies():
    from core.constants import DEFAULT_SETTINGS
    from core.models import SiteSettings
    a = SiteSettings()
    a.nav_labels["gallery"] = "ИЗМЕНЕНО"
    a.amenities.append({"icon": "x", "name": "y"})
    assert SiteSettings().nav_labels["gallery"] != "ИЗМЕНЕНО"
    assert DEFAULT_SETTINGS["nav_labels"]["gallery"] != "ИЗМЕНЕНО"
    assert len(DEFAULT_SETTINGS["amenities"]) == len(SiteSettings().amenities)
