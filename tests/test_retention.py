"""Хранение данных брони: упаковка в архив с паролем, удаление по сроку, очистка отменённых броней."""
import json
import os
import types
from datetime import date

import pytest

pyzipper = pytest.importorskip("pyzipper")

import core.db as db
import core.passports as passports
from core import retention


@pytest.fixture
def env(tmp_path, monkeypatch):
    contracts = tmp_path / "contracts"; contracts.mkdir()
    pdir = tmp_path / "passports"; pdir.mkdir()
    monkeypatch.setattr(retention, "CONTRACTS_DIR", str(contracts))
    monkeypatch.setattr(retention, "PASSPORT_DIR", str(pdir))
    monkeypatch.setattr(retention, "ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setattr(retention, "RETENTION_FILE", str(tmp_path / "retention.json"))
    monkeypatch.setattr(passports, "PASSPORT_MAP_FILE", str(tmp_path / "pm.json"))
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "b.db"))
    monkeypatch.setattr(retention, "_today", lambda: date(2026, 12, 1))
    monkeypatch.setattr(retention, "_password", lambda: "pw")
    monkeypatch.setattr(retention, "_password_warned", False)
    return types.SimpleNamespace(contracts=contracts, pdir=pdir, archive=tmp_path / "archive")


def add_booking(ref, status="confirmed", check_out="2026-10-01", deposit_returned=1, signed_at="2026-09-01 10:00:00"):
    conn = db.get_db()
    conn.execute("INSERT INTO bookings (username, status, check_out, deposit_returned, signed_at) VALUES (?,?,?,?,?)",
                 (ref, status, check_out, deposit_returned, signed_at))
    conn.commit()
    conn.close()


def add_files(env, ref, signed=True):
    names = [ref + ".txt", ref + ".pdf", ref + "_soglasie_pd.pdf"] + ([ref + "_podpisan.pdf"] if signed else [])
    for n in names:
        (env.contracts / n).write_bytes(b"data " + n.encode())
    (env.pdir / f"{ref}_1.jpg").write_bytes(b"photo1")
    (env.pdir / f"{ref}_2.jpg").write_bytes(b"photo2")
    pm = passports.load_passport_map()
    pm[ref] = {"main": f"{ref}_1.jpg", "reg1": f"{ref}_2.jpg"}
    passports.save_passport_map(pm)
    return names


def archive_names(path):
    with pyzipper.AESZipFile(path) as zf:
        zf.setpassword(b"pw")
        return set(zf.namelist())


def set_days(pack=0, delete=0, purge=False):
    retention.save_settings(pack, delete, purge)


def test_settings_default_off_and_validation(env):
    assert retention.load_settings() == {"pack_days": 0, "delete_days": 0, "purge_cancelled": False}
    with pytest.raises(ValueError):
        retention.save_settings(30, 20, False)
    assert retention.save_settings(30, 90, True) == {"pack_days": 30, "delete_days": 90, "purge_cancelled": True}
    assert retention.save_settings(0, 10, False)["delete_days"] == 10   # упаковка выключена, архивы всё равно можно удалять по сроку


def test_nothing_happens_by_default(env):
    add_booking("GP-AAA111")
    add_files(env, "GP-AAA111")
    assert retention.run_retention() == {"packed": 0, "archives_deleted": 0, "purged": 0, "errors": 0}
    assert (env.contracts / "GP-AAA111_podpisan.pdf").exists() and (env.pdir / "GP-AAA111_1.jpg").exists()


def test_pack_confirmed_booking_with_returned_deposit(env):
    add_booking("GP-AAA111")
    names = add_files(env, "GP-AAA111")
    set_days(pack=30)
    assert retention.run_retention()["packed"] == 1
    # обычных файлов больше нет, запись о фото убрана
    assert not any((env.contracts / n).exists() for n in names)
    assert not (env.pdir / "GP-AAA111_1.jpg").exists() and "GP-AAA111" not in passports.load_passport_map()
    # архив открывается с паролем и содержит всё
    arch = env.archive / "GP-AAA111.zip"
    got = archive_names(str(arch))
    assert {"contracts/" + n for n in names} <= got
    assert {"passports/GP-AAA111_1.jpg", "passports/GP-AAA111_2.jpg", "meta.json"} <= got
    with pytest.raises(Exception):
        with pyzipper.AESZipFile(str(arch)) as zf:   # без пароля не читается
            zf.read("meta.json")
    assert retention.list_archived()["GP-AAA111"]["archives"] == ["GP-AAA111.zip"]


def test_not_packed_without_returned_deposit_or_before_term_or_other_status(env):
    add_booking("GP-NODEP1", deposit_returned=0); add_files(env, "GP-NODEP1")
    add_booking("GP-FRESH1", check_out="2026-11-20"); add_files(env, "GP-FRESH1")   # выезд 11 дней назад, срок 30
    add_booking("GP-WAIT01", status="waiting_payment"); add_files(env, "GP-WAIT01")
    set_days(pack=30)
    assert retention.run_retention()["packed"] == 0
    assert (env.contracts / "GP-NODEP1_podpisan.pdf").exists()
    assert (env.contracts / "GP-FRESH1_podpisan.pdf").exists()
    assert (env.contracts / "GP-WAIT01_podpisan.pdf").exists()


def test_no_password_means_no_packing(env, monkeypatch):
    monkeypatch.setattr(retention, "_password", lambda: "")
    add_booking("GP-AAA111"); add_files(env, "GP-AAA111")
    set_days(pack=30)
    assert retention.run_retention()["packed"] == 0
    assert (env.contracts / "GP-AAA111_podpisan.pdf").exists() and not env.archive.exists()


def test_failed_verification_keeps_originals(env, monkeypatch):
    monkeypatch.setattr(retention, "_verify_archive", lambda *a, **k: False)
    add_booking("GP-AAA111"); add_files(env, "GP-AAA111")
    set_days(pack=30)
    r = retention.run_retention()
    assert r["packed"] == 0 and r["errors"] == 1
    assert (env.contracts / "GP-AAA111_podpisan.pdf").exists() and (env.pdir / "GP-AAA111_1.jpg").exists()
    assert "GP-AAA111" in passports.load_passport_map()
    assert not list(env.archive.glob("*.zip*")) if env.archive.exists() else True   # временный файл убран


def test_second_pack_never_overwrites_first_archive(env):
    add_booking("GP-AAA111"); add_files(env, "GP-AAA111")
    set_days(pack=30)
    retention.run_retention()
    (env.contracts / "GP-AAA111_podpisan.pdf").write_bytes(b"regenerated")   # файл появился снова (например, договор отправили повторно)
    retention.run_retention()
    assert (env.archive / "GP-AAA111.zip").exists() and (env.archive / "GP-AAA111_2.zip").exists()
    assert retention.list_archived()["GP-AAA111"]["archives"] == ["GP-AAA111.zip", "GP-AAA111_2.zip"]


def test_archives_deleted_after_term(env):
    add_booking("GP-OLD001", check_out="2026-08-01"); add_files(env, "GP-OLD001")
    add_booking("GP-NEW001", check_out="2026-10-01"); add_files(env, "GP-NEW001")
    set_days(pack=30)
    retention.run_retention()
    assert (env.archive / "GP-OLD001.zip").exists() and (env.archive / "GP-NEW001.zip").exists()
    set_days(pack=30, delete=100)    # от 1 августа прошло 122 дня, от 1 октября — 61
    assert retention.run_retention()["archives_deleted"] == 1
    assert not (env.archive / "GP-OLD001.zip").exists() and (env.archive / "GP-NEW001.zip").exists()
    assert list(retention.list_archived()) == ["GP-NEW001"]


def test_purge_cancelled_unsigned_only(env):
    add_booking("GP-CNL001", status="cancelled", deposit_returned=0, signed_at=""); add_files(env, "GP-CNL001", signed=False)
    add_booking("GP-CNL002", status="cancelled", deposit_returned=0, signed_at="2026-09-01 10:00:00"); add_files(env, "GP-CNL002")
    add_booking("GP-OK0001", status="confirmed", deposit_returned=0); add_files(env, "GP-OK0001")
    set_days(purge=False)
    assert retention.run_retention()["purged"] == 0 and (env.contracts / "GP-CNL001.txt").exists()   # переключатель выключен
    set_days(purge=True)
    assert retention.run_retention()["purged"] == 1
    assert not (env.contracts / "GP-CNL001.txt").exists() and not (env.pdir / "GP-CNL001_1.jpg").exists()
    assert "GP-CNL001" not in passports.load_passport_map()
    assert (env.contracts / "GP-CNL002_podpisan.pdf").exists() and (env.pdir / "GP-CNL002_1.jpg").exists()   # подписанная — не трогаем
    assert (env.contracts / "GP-OK0001_podpisan.pdf").exists()                                               # подтверждённая — не трогаем


def test_preview_matches_what_will_happen_and_changes_nothing(env):
    add_booking("GP-AAA111"); add_files(env, "GP-AAA111")
    add_booking("GP-CNL001", status="cancelled", deposit_returned=0, signed_at=""); add_files(env, "GP-CNL001", signed=False)
    p = retention.preview(30, 0, False)
    assert p == {"to_pack": 1, "archives_to_delete": 0, "cancelled_with_files": 1}
    assert retention.preview(0, 0, False)["to_pack"] == 0
    assert (env.contracts / "GP-AAA111_podpisan.pdf").exists() and (env.contracts / "GP-CNL001.txt").exists()
    with pytest.raises(ValueError):
        retention.preview(30, 10, False)


def test_delete_archive_removes_files_and_index(env):
    add_booking("GP-AAA111"); add_files(env, "GP-AAA111")
    set_days(pack=30)
    retention.run_retention()
    assert retention.delete_archive("GP-AAA111") == 1
    assert not (env.archive / "GP-AAA111.zip").exists() and retention.list_archived() == {}
    assert retention.delete_archive("GP-AAA111") == 0   # повторно безопасно
