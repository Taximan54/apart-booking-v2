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
        assert "bookings.db" in names
        # договоры и паспорта в основную копию не входят — они в отдельном архиве документов
        assert not any(n.startswith(("contracts/", "passports/")) for n in names)
    docs = [f for f in os.listdir(os.path.dirname(path)) if f.startswith("backup_docs_")]
    assert len(docs) == 1
    dpath = os.path.join(os.path.dirname(path), docs[0])
    assert bk.is_backup_encrypted(dpath)
    with pyzipper.AESZipFile(dpath) as zf:
        zf.setpassword("Пароль-123".encode("utf-8"))
        assert {"contracts/GP-AAA111_podpisan.pdf", "passports/passport_x.jpg"} <= set(zf.namelist())
        assert zf.read("passports/passport_x.jpg") == b"JPEGDATA-SECRET"
    # с неверным паролем и без пароля — нет
    with pyzipper.AESZipFile(dpath) as zf:
        zf.setpassword(b"wrong")
        with pytest.raises(RuntimeError):
            zf.read("passports/passport_x.jpg")
        zf.setpassword(None)
        with pytest.raises(RuntimeError):
            zf.read("contracts/GP-AAA111_podpisan.pdf")
    # данные паспорта не лежат в архивах открытым текстом
    assert b"JPEGDATA-SECRET" not in open(dpath, "rb").read()
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


def test_rotation_counts_main_docs_and_photo_archives_separately(env, monkeypatch):
    bk, data = env
    (data / "backups").mkdir()
    for d in ("2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05"):
        (data / "backups" / f"backup_{d}_00-00.zip").write_bytes(b"old")
        (data / "backups" / f"backup_docs_{d}_00-00.zip").write_bytes(b"old")
        (data / "backups" / f"backup_photos_{d}_00-00.zip").write_bytes(b"old")
    monkeypatch.setattr(bk, "BACKUP_KEEP_COUNT", 2)
    bk.create_backup_zip()   # свежих архивов документов и фото нет по mtime? файлы только что созданы -> новые не делаются
    names = os.listdir(data / "backups")
    main = [n for n in names if not n.startswith(("backup_docs_", "backup_photos_"))]
    docs = [n for n in names if n.startswith("backup_docs_")]
    photos = [n for n in names if n.startswith("backup_photos_")]
    assert len(main) == 2 and len(docs) == 3 and len(photos) == 2
    assert "backup_2020-01-01_00-00.zip" not in main
    assert "backup_docs_2020-01-01_00-00.zip" not in docs and "backup_docs_2020-01-05_00-00.zip" in docs
    assert "backup_photos_2020-01-04_00-00.zip" in photos


def test_docs_and_photos_archives_are_made_rarely(env, monkeypatch):
    bk, data = env
    (data / "photos").mkdir()
    (data / "photos" / "a.jpg").write_bytes(b"x")
    bk.create_backup_zip()
    bdir = data / "backups"
    docs = [f for f in os.listdir(bdir) if f.startswith("backup_docs_")]
    photos = [f for f in os.listdir(bdir) if f.startswith("backup_photos_")]
    assert len(docs) == 1 and len(photos) == 1
    # свежие архивы — повторно не делаются (подменяем время, чтобы имя было другим)
    monkeypatch.setattr(bk, "now_nsk", lambda: __import__("datetime").datetime(2099, 1, 1, 4, 0))
    bk.create_backup_zip()
    assert [f for f in os.listdir(bdir) if f.startswith("backup_docs_")] == docs
    assert [f for f in os.listdir(bdir) if f.startswith("backup_photos_")] == photos
    # документы старше 14 дней — делаются заново, фото (моложе 30 дней) — нет
    old = __import__("time").time() - 15 * 86400
    os.utime(bdir / docs[0], (old, old)); os.utime(bdir / photos[0], (old, old))
    monkeypatch.setattr(bk, "now_nsk", lambda: __import__("datetime").datetime(2099, 1, 2, 4, 0))
    bk.create_backup_zip()
    assert len([f for f in os.listdir(bdir) if f.startswith("backup_docs_")]) == 2
    assert len([f for f in os.listdir(bdir) if f.startswith("backup_photos_")]) == 1
    # «Копия сейчас» (force_all) делает всё сразу
    monkeypatch.setattr(bk, "now_nsk", lambda: __import__("datetime").datetime(2099, 1, 3, 4, 0))
    bk.create_backup_zip(True)
    assert len([f for f in os.listdir(bdir) if f.startswith("backup_docs_")]) == 3
    assert len([f for f in os.listdir(bdir) if f.startswith("backup_photos_")]) == 2


# ---------- настройки копий (backup_settings.json) ----------

def test_backup_settings_defaults_without_file(env):
    bk, data = env
    s = bk.get_backup_settings()
    assert s == {"daily_keep": bk.BACKUP_KEEP_COUNT, "docs_days": 14, "docs_keep": 3,
                 "photos_days": 30, "photos_keep": 2}
    assert not (data / "backup_settings.json").exists(), "чтение настроек файл не создаёт"


def test_backup_settings_save_and_read_back(env):
    bk, data = env
    new = {"daily_keep": 7, "docs_days": 0, "docs_keep": 1, "photos_days": 90, "photos_keep": 5}
    assert bk.save_backup_settings(new) == new
    assert (data / "backup_settings.json").exists()
    assert bk.get_backup_settings() == new


@pytest.mark.parametrize("bad", [
    {"daily_keep": 0},          # хранить ноль ежедневных копий нельзя
    {"daily_keep": 61},
    {"docs_days": -1},
    {"docs_days": 366},
    {"docs_keep": 0},
    {"photos_keep": 21},
    {"photos_days": "abc"},
    {"photos_days": 1.5},
    {"docs_days": True},
    {"docs_days": None},
])
def test_backup_settings_rejects_bad_values(env, bad):
    bk, data = env
    ok = {"daily_keep": 14, "docs_days": 14, "docs_keep": 3, "photos_days": 30, "photos_keep": 2}
    with pytest.raises(ValueError):
        bk.save_backup_settings({**ok, **bad})
    assert not (data / "backup_settings.json").exists(), "при ошибке ничего не записывается"


def test_backup_settings_missing_field_is_rejected(env):
    bk, _ = env
    with pytest.raises(ValueError):
        bk.save_backup_settings({"daily_keep": 14})
    with pytest.raises(ValueError):
        bk.save_backup_settings("не словарь")


def test_backup_settings_broken_file_falls_back_to_defaults(env):
    bk, data = env
    (data / "backup_settings.json").write_text("{не json", encoding="utf-8")
    assert bk.get_backup_settings()["docs_days"] == 14
    # частично верный файл: хорошие поля берутся, плохие — по умолчанию
    (data / "backup_settings.json").write_text('{"docs_days": 5, "photos_days": -3, "daily_keep": "x"}', encoding="utf-8")
    s = bk.get_backup_settings()
    assert s["docs_days"] == 5 and s["photos_days"] == 30 and s["daily_keep"] == bk.BACKUP_KEEP_COUNT


def test_zero_days_disables_docs_and_photos_even_for_force(env, monkeypatch):
    bk, data = env
    (data / "photos").mkdir()
    (data / "photos" / "a.jpg").write_bytes(b"x")
    bk.save_backup_settings({"daily_keep": 14, "docs_days": 0, "docs_keep": 3, "photos_days": 0, "photos_keep": 2})
    path = bk.create_backup_zip(True)
    names = os.listdir(os.path.dirname(path))
    assert not [n for n in names if n.startswith(("backup_docs_", "backup_photos_"))]
    assert os.path.exists(path), "основная копия делается всегда"


def test_custom_interval_and_keep_are_used(env, monkeypatch):
    bk, data = env
    bk.save_backup_settings({"daily_keep": 1, "docs_days": 3, "docs_keep": 1, "photos_days": 30, "photos_keep": 2})
    bk.create_backup_zip()
    bdir = data / "backups"
    docs = [f for f in os.listdir(bdir) if f.startswith("backup_docs_")]
    assert len(docs) == 1
    # архив моложе 3 дней — заново не делается
    monkeypatch.setattr(bk, "now_nsk", lambda: __import__("datetime").datetime(2099, 1, 1, 4, 0))
    bk.create_backup_zip()
    assert [f for f in os.listdir(bdir) if f.startswith("backup_docs_")] == docs
    # старше 3 дней — делается новый, а старый удаляется (хранить 1); основных копий тоже одна
    old = __import__("time").time() - 4 * 86400
    os.utime(bdir / docs[0], (old, old))
    monkeypatch.setattr(bk, "now_nsk", lambda: __import__("datetime").datetime(2099, 1, 2, 4, 0))
    bk.create_backup_zip()
    docs_now = [f for f in os.listdir(bdir) if f.startswith("backup_docs_")]
    assert len(docs_now) == 1 and docs_now != docs
    main = [f for f in os.listdir(bdir) if not f.startswith(("backup_docs_", "backup_photos_"))]
    assert len(main) == 1
