"""
Подписанный договор с фото паспорта: PDF должен собираться при любых
пропорциях фото, на фото должна быть защитная сетка.
"""
import json
import os

import pytest
from PIL import Image, ImageDraw

BOOKING = {
    "username": "TESTREF", "id": 1, "guest_name": "Иванов Иван", "guest_phone": "+79990000000",
    "guest_email": "a@b.c", "passport": "1234 567890", "check_in": "2026-10-10",
    "check_out": "2026-10-12", "nights": 2, "total_price": 9000,
    "signed_at": "2026-10-04 12:00:00", "sign_ip": "1.1.1.1", "status": "confirmed",
}

# (ширина, высота) двух фото: обычное 3:4, горизонтальное, вытянутое 9:16, очень вытянутое
CASES = {
    "normal": [(1350, 1800), (1350, 1800)],
    "wide": [(1800, 1200), (1800, 1100)],
    "tall_9_16": [(1012, 1800), (1350, 1800)],
    "extreme": [(500, 1800), (1350, 1800)],
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Подменяет папки данных на временные, чтобы тест не трогал боевые файлы."""
    import core.contract_docs as cd
    import core.passports as pp
    import core.signing as sg

    pdir = tmp_path / "passports"
    pdir.mkdir()
    cdir = tmp_path / "contracts"
    cdir.mkdir()
    map_file = tmp_path / "passport_photos.json"
    monkeypatch.setattr(sg, "PASSPORT_DIR", str(pdir))
    monkeypatch.setattr(pp, "PASSPORT_MAP_FILE", str(map_file))
    monkeypatch.setattr(cd, "CONTRACTS_DIR", str(cdir))
    return pdir, map_file


def _make_photos(pdir, map_file, sizes):
    entry = {}
    for slot, (w, h) in zip(("main", "reg1"), sizes):
        name = f"p_{slot}.jpg"
        im = Image.new("RGB", (w, h), (230, 225, 215))
        ImageDraw.Draw(im).rectangle((30, 30, w - 30, h - 30), outline=(60, 60, 60), width=6)
        im.save(pdir / name, quality=85)
        entry[slot] = name
    map_file.write_text(json.dumps({"TESTREF": entry}), encoding="utf-8")


@pytest.mark.parametrize("case", sorted(CASES))
def test_signed_pdf_is_built_with_photos(isolated, case):
    from core.signing import _passport_photos_with_grid, generate_signed_contract_pdf
    pdir, map_file = isolated
    _make_photos(pdir, map_file, CASES[case])
    assert len(_passport_photos_with_grid("TESTREF")) == 2, "фото с сеткой не получены (сетка сломана)"
    path = generate_signed_contract_pdf(dict(BOOKING))
    assert os.path.exists(path) and os.path.getsize(path) > 10_000
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_signed_pdf_is_built_without_photos(isolated):
    from core.signing import generate_signed_contract_pdf
    path = generate_signed_contract_pdf(dict(BOOKING))
    assert os.path.exists(path)


@pytest.mark.parametrize("size", [(800, 600), (1350, 1800), (1800, 1200)])
def test_watermark_changes_picture_and_keeps_size(size):
    """Размеры как у реальных фото с телефона: на больших фото сетка раньше падала с ошибкой."""
    from core.passports import apply_passport_watermark
    src = Image.new("RGB", size, (230, 225, 215))
    out = apply_passport_watermark(src)
    assert out.size == src.size and out.mode == "RGB"
    assert list(out.getdata()) != list(src.getdata()), "сетка не наложилась"
