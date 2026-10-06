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
    path = bk.create_backup_zip()
    sent = []
    monkeypatch.setattr(bk, "send_email", lambda to, subject, html, attachments=None: sent.append((to, html, attachments)))
    result = asyncio.run(bk.send_backup_everywhere(path))
    assert result["email"] is True and result["encrypted"] is True
    assert len(sent) == 1 and sent[0][2][0]["filepath"] == path
    assert "защищён паролем" in sent[0][1]
    assert "Пароль-123" not in sent[0][1], "пароль не должен попадать в письмо"


def test_is_backup_encrypted_handles_broken_file(tmp_path):
    from core.backup import is_backup_encrypted
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert is_backup_encrypted(str(bad)) is False
