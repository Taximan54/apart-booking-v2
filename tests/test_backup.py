"""Резервные копии: шифрование паролем и запрет отправки открытой копии."""
import asyncio
import os

import pytest

pyzipper = pytest.importorskip("pyzipper")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Подменяет все пути на временные: боевые данные и копии не затрагиваются."""
    import core.backup as bk
    data = tmp_path / "data"
    (data / "contracts").mkdir(parents=True)
    (data / "passports").mkdir()
    (data / "bookings.db").write_bytes(b"SQLITE-DATA")
    (data / "contracts" / "GP-AAA111_podpisan.pdf").write_bytes(b"%PDF-contract")
    (data / "passports" / "passport_x.jpg").write_bytes(b"JPEGDATA-SECRET")
    monkeypatch.setattr(bk, "BACKUP_DIR", str(data / "backups"))
    monkeypatch.setattr(bk, "DB_FILE", str(data / "bookings.db"))
    monkeypatch.setattr(bk, "CONTRACTS_DIR", str(data / "contracts"))
    monkeypatch.setattr(bk, "PASSPORT_DIR", str(data / "passports"))
    for name in ("PRICE_FILE", "CONTACTS_FILE", "PAYMENT_FILE", "PROMO_FILE", "CONTRACT_FILE",
                 "PASSPORT_MAP_FILE", "SETTINGS_FILE", "DISCOUNTS_FILE", "PLACES_FILE", "LANDLORD_FILE"):
        monkeypatch.setattr(bk, name, str(data / "nonexistent.json"))
    monkeypatch.setattr(bk, "BACKUP_PASSWORD_FILE", str(data / "backup_password.txt"))
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", "", raising=False)
    return bk, data


def test_password_from_config_wins_over_file(env, monkeypatch):
    bk, data = env
    (data / "backup_password.txt").write_text("из-файла\n", encoding="utf-8")
    assert bk.get_backup_password() == "из-файла"
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", " из-config ", raising=False)
    assert bk.get_backup_password() == "из-config"


def test_no_password_gives_empty_string(env):
    bk, _ = env
    assert bk.get_backup_password() == ""


def test_backup_is_encrypted_with_password(env, monkeypatch):
    bk, _ = env
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", "Пароль-123", raising=False)
    path = bk.create_backup_zip()
    assert bk.is_backup_encrypted(path)
    # с верным паролем всё открывается, содержимое то же
    with pyzipper.AESZipFile(path) as zf:
        zf.setpassword("Пароль-123".encode("utf-8"))
        names = set(zf.namelist())
        assert {"bookings.db", "contracts/GP-AAA111_podpisan.pdf", "passports/passport_x.jpg"} <= names
        assert zf.read("passports/passport_x.jpg") == b"JPEGDATA-SECRET"
    # с неверным паролем и без пароля — нет
    with pyzipper.AESZipFile(path) as zf:
        zf.setpassword(b"wrong")
        with pytest.raises(RuntimeError):
            zf.read("passports/passport_x.jpg")
        zf.setpassword(None)
        with pytest.raises(RuntimeError):
            zf.read("bookings.db")
    # исходные данные паспорта не лежат в архиве открытым текстом
    assert b"JPEGDATA-SECRET" not in open(path, "rb").read()


def test_backup_without_password_is_plain_and_not_sent(env, monkeypatch):
    bk, _ = env
    path = bk.create_backup_zip()
    assert os.path.exists(path) and not bk.is_backup_encrypted(path)
    calls = []
    monkeypatch.setattr(bk, "send_email", lambda *a, **k: calls.append(("email", a)))
    result = asyncio.run(bk.send_backup_everywhere(path))
    assert result == {"telegram": False, "email": False, "encrypted": False}
    assert calls == [], "открытая копия не должна уходить на почту"


def test_encrypted_backup_is_sent_by_email(env, monkeypatch):
    bk, _ = env
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", "Пароль-123", raising=False)
    monkeypatch.setattr(bk, "ADMIN_IDS", [])                         # Telegram в тесте не трогаем
    monkeypatch.setattr(bk, "get_site_settings_dict", lambda: {})
    monkeypatch.setattr(bk, "LANDLORD_EMAIL", "owner@test.ru")      # «Контакты» в тесте пустые, запасная почта задаётся здесь
    path = bk.create_backup_zip()
    sent = []
    monkeypatch.setattr(bk, "send_email", lambda to, subject, html, attachments=None: sent.append((to, html, attachments)))
    result = asyncio.run(bk.send_backup_everywhere(path))
    assert result["email"] is True and result["encrypted"] is True
    assert len(sent) == 1 and sent[0][0] == "owner@test.ru" and sent[0][2][0]["filepath"] == path
    assert "защищён паролем" in sent[0][1]
    assert "Пароль-123" not in sent[0][1], "пароль не должен попадать в письмо"


def test_is_backup_encrypted_handles_broken_file(tmp_path):
    from core.backup import is_backup_encrypted
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert is_backup_encrypted(str(bad)) is False


def test_backup_includes_other_data_files_and_property_folders(env, monkeypatch):
    """Файлы вроде booking_rules.json, chat_faq.json, contract_settings.json, photos/ и properties/<id>/ попадают в копию."""
    bk, data = env
    (data / "photos").mkdir()
    (data / "properties" / "2").mkdir(parents=True)
    (data / "chat_faq.json").write_text("{}", encoding="utf-8")
    (data / "booking_rules.json").write_text("{}", encoding="utf-8")
    (data / "contract_template.txt.backup_before_placeholders").write_text("old", encoding="utf-8")
    (data / "photos" / "a.jpg").write_bytes(b"PHOTO")
    (data / "properties" / "2" / "contract_settings.json").write_text("{}", encoding="utf-8")
    (data / "properties" / "2" / "ical.json").write_text("{}", encoding="utf-8")
    (data / "backup_password.txt").write_text("secret-pass", encoding="utf-8")
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", "Пароль-123", raising=False)
    path = bk.create_backup_zip()
    with pyzipper.AESZipFile(path) as zf:
        zf.setpassword("Пароль-123".encode("utf-8"))
        names = zf.namelist()
    assert {"chat_faq.json", "booking_rules.json",
            "properties/2/contract_settings.json", "properties/2/ical.json"} <= set(names)
    assert "photos/a.jpg" not in names, "фото лежат в отдельном архиве"
    assert "backup_password.txt" not in names, "пароль копий не кладём в архив"
    assert not any(".backup_" in n for n in names), "старые резервные версии шаблонов не нужны"
    assert not any(n.startswith("backups/") for n in names), "старые копии не кладём в новую"
    assert len(names) == len(set(names)), "дубликатов в архиве быть не должно"


def test_photos_go_to_separate_encrypted_archive(env, monkeypatch):
    bk, data = env
    (data / "photos").mkdir()
    (data / "photos" / "a.jpg").write_bytes(b"PHOTO-SECRET")
    monkeypatch.setattr(bk.config, "BACKUP_PASSWORD", "Пароль-123", raising=False)
    path = bk.create_backup_zip()
    assert os.path.basename(path).startswith("backup_") and "photos" not in os.path.basename(path)
    photos = [f for f in os.listdir(data / "backups") if f.startswith("backup_photos_")]
    assert len(photos) == 1
    ppath = str(data / "backups" / photos[0])
    assert bk.is_backup_encrypted(ppath)
    with pyzipper.AESZipFile(ppath) as zf:
        zf.setpassword("Пароль-123".encode("utf-8"))
        assert zf.read("photos/a.jpg") == b"PHOTO-SECRET"
    assert b"PHOTO-SECRET" not in open(ppath, "rb").read()


def test_no_photos_no_photo_archive(env):
    bk, data = env
    bk.create_backup_zip()
    assert not [f for f in os.listdir(data / "backups") if f.startswith("backup_photos_")]


def test_rotation_counts_main_and_photo_archives_separately(env, monkeypatch):
    bk, data = env
    (data / "photos").mkdir()
    (data / "photos" / "a.jpg").write_bytes(b"x")
    (data / "backups").mkdir()
    for d in ("2020-01-01", "2020-01-02", "2020-01-03"):
        (data / "backups" / f"backup_{d}_00-00.zip").write_bytes(b"old")
        (data / "backups" / f"backup_photos_{d}_00-00.zip").write_bytes(b"old")
    monkeypatch.setattr(bk, "BACKUP_KEEP_COUNT", 2)
    bk.create_backup_zip()
    names = os.listdir(data / "backups")
    main = [n for n in names if not n.startswith("backup_photos_")]
    photos = [n for n in names if n.startswith("backup_photos_")]
    assert len(main) == 2 and len(photos) == 2
    assert "backup_2020-01-01_00-00.zip" not in main and "backup_photos_2020-01-01_00-00.zip" not in photos
