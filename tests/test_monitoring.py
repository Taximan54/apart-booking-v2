"""Мониторинг сбоев: проверки, письма (подменены, настоящие не уходят), журнал инцидентов."""
import os
from datetime import datetime, timedelta

import pytest

from core import mailer, monitoring as mon

T0 = datetime(2026, 11, 11, 12, 0, 0)


def h(hours):
    return T0 + timedelta(hours=hours)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(mon, "SETTINGS_FILE", str(tmp_path / "monitoring.json"))
    monkeypatch.setattr(mon, "STATE_FILE", str(tmp_path / "incidents.json"))
    monkeypatch.setattr(mon, "BACKUP_DIR", str(tmp_path / "backups"))
    os.makedirs(tmp_path / "backups")
    ctx = {"platforms": [], "disk": 50.0, "db_ok": True, "password": True, "mails": [], "backup_age": None}
    monkeypatch.setattr(mon, "list_properties", lambda: [{"id": 1, "name": "Основной", "active": True}])
    monkeypatch.setattr(mon, "list_platforms", lambda pid: ctx["platforms"])
    monkeypatch.setattr(mon, "_disk_free_percent", lambda: ctx["disk"])
    monkeypatch.setattr(mon, "_backup_password_set", lambda: ctx["password"])
    monkeypatch.setattr(mon, "_backup_age_hours", lambda: ctx["backup_age"])
    monkeypatch.setattr(mon, "alert_recipient", lambda: "admin@example.com")
    monkeypatch.setattr(mon.repo, "count_bookings", lambda pid: 0 if ctx["db_ok"] else (_ for _ in ()).throw(RuntimeError("db down")), raising=False)
    monkeypatch.setattr(mailer, "STATUS", {"last_ok_ts": 0.0, "last_error_ts": 0.0, "last_error": ""})
    ctx["backup_age"] = 2.0
    ctx["send"] = lambda kind, inc: ctx["mails"].append((kind, inc["key"]))
    return ctx


def run(env, now, tasks=None):
    tasks = {"send_notifications", "ical_sync_loop"} if tasks is None else tasks
    return mon.run_checks(tasks, now=now, send=env["send"])


def test_all_ok_no_incidents(env):
    state = run(env, T0)
    assert state["open"] == [] and env["mails"] == []


def test_settings_clamped_and_saved(env):
    s = mon.save_settings({"ical_hours": 999, "disk_free_percent": 1, "enabled": False})
    assert s["ical_hours"] == 48 and s["disk_free_percent"] == 5 and s["enabled"] is False
    assert mon.load_settings()["backup_hours"] == 26


def test_disabled_does_nothing(env):
    mon.save_settings({"enabled": False})
    env["disk"] = 1.0
    run(env, T0)
    assert env["mails"] == []


def test_disk_alert_once_remind_and_recover(env):
    env["disk"] = 10.0
    run(env, T0)
    run(env, h(1))                      # повторное письмо сразу не приходит
    assert env["mails"] == [("open", "disk:low")]
    run(env, h(6))                      # напоминание через 6 часов
    assert env["mails"][-1] == ("remind", "disk:low")
    env["disk"] = 40.0
    state = run(env, h(7))
    assert env["mails"][-1] == ("resolved", "disk:low")
    assert state["open"] == [] and state["history"][0]["key"] == "disk:low"


def test_incident_survives_restart_without_new_mail(env):
    env["disk"] = 10.0
    run(env, T0)
    run(env, h(1))   # «перезапуск»: состояние читается из файла
    assert len(env["mails"]) == 1


def test_ical_failing_needs_grace_period(env):
    env["platforms"] = [{"source": "avito", "name": "Авито", "url": "http://x", "enabled": True,
                         "last_sync": {"ok": False, "at": "2026-11-11 12:00", "error": "таймаут"}}]
    run(env, T0)
    run(env, h(2))
    assert env["mails"] == []
    run(env, h(3))
    assert env["mails"] == [("open", "ical:1:avito")]
    env["platforms"][0]["last_sync"] = {"ok": True, "at": "2026-11-11 15:30"}
    run(env, h(4))
    assert env["mails"][-1] == ("resolved", "ical:1:avito")


def test_ical_stale_success_report(env):
    env["platforms"] = [{"source": "yandex", "name": "Яндекс", "url": "http://x", "enabled": True,
                         "last_sync": {"ok": True, "at": "2026-11-11 07:00"}}]
    run(env, T0)    # прошло 5 часов
    assert env["mails"] == [("open", "ical:1:yandex")]


def test_ical_disabled_or_no_url_ignored(env):
    env["platforms"] = [{"source": "a", "name": "A", "url": "", "enabled": True, "last_sync": None},
                        {"source": "b", "name": "B", "url": "http://x", "enabled": False, "last_sync": None}]
    run(env, h(10))
    assert env["mails"] == []


def test_backup_age_ignores_server_timezone(tmp_path, monkeypatch):
    """Свежий файл копии считается свежим при любом часовом поясе сервера (раньше сравнение с поясом Новосибирска давало лишние 7 часов)."""
    monkeypatch.setattr(mon, "BACKUP_DIR", str(tmp_path))
    assert mon._backup_age_hours() is None
    path = tmp_path / "backup_2026-11-11_04-12.zip"
    path.write_bytes(b"x")
    import time as _t
    os.utime(path, (_t.time() - 19 * 3600, _t.time() - 19 * 3600))
    age = mon._backup_age_hours()
    assert 18.9 < age < 19.1


def test_backup_stale_and_password(env):
    env["backup_age"] = 30.0
    env["password"] = False
    run(env, T0)
    assert {k for _, k in env["mails"]} == {"backup:stale", "backup:password"}


def test_no_backups_after_grace(env):
    env["backup_age"] = None
    run(env, T0)
    assert env["mails"] == []
    run(env, h(26))
    assert env["mails"] == [("open", "backup:none")]


def test_db_down(env):
    env["db_ok"] = False
    run(env, T0)
    assert env["mails"] == [("open", "db:error")]


def test_mail_failure_detected(env):
    mailer.STATUS.update(last_error_ts=100.0, last_error="auth failed")
    run(env, T0)
    assert env["mails"] == [("open", "mail:send")]
    mailer.STATUS["last_ok_ts"] = 200.0
    run(env, h(1))
    assert env["mails"][-1] == ("resolved", "mail:send")


def test_stopped_task_detected(env):
    run(env, T0, tasks={"send_notifications"})
    assert env["mails"] == [("open", "task:ical_sync_loop")]


def test_send_failure_does_not_break(env):
    env["disk"] = 5.0
    def boom(kind, inc): raise RuntimeError("smtp")
    mon.run_checks(set(mon.WATCHED_TASKS), now=T0, send=boom)
    assert len(mon.public_state()["open"]) == 1
