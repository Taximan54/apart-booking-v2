"""Тесты не должны отправлять настоящие письма (см. корневой conftest.py)."""
import smtplib


def test_smtp_is_blocked_during_tests():
    assert getattr(smtplib.SMTP_SSL, "is_test_stub", False)
    assert getattr(smtplib.SMTP, "is_test_stub", False)


def test_mailer_does_not_reach_real_smtp(monkeypatch):
    import core.mailer as mailer
    monkeypatch.setattr(mailer, "MAIL_PASSWORD", "x")
    before = len(smtplib.SMTP_SSL.attempts)
    mailer.send_email("a@b.c", "Тема", "<p>html</p>")
    assert len(smtplib.SMTP_SSL.attempts) == before + 1
