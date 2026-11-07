"""Общая настройка тестов: тесты не должны читать настоящие данные сервера.
Данные объекта для договора (/data/contract_settings.json) на время каждого теста подменяются пустым временным файлом.
Настоящая отправка писем (smtplib) на время всех тестов заблокирована."""
import smtplib

import pytest


class _BlockedSMTP:
    """Заглушка вместо smtplib.SMTP_SSL / SMTP: ничего не отправляет, только запоминает попытки."""
    is_test_stub = True
    attempts = []

    def __init__(self, *args, **kwargs):
        _BlockedSMTP.attempts.append(args)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture(scope="session", autouse=True)
def _block_real_email():
    # На весь запуск, а не на один тест: письма уходят в фоновых потоках и могут
    # добежать уже после окончания теста.
    mp = pytest.MonkeyPatch()
    mp.setattr(smtplib, "SMTP_SSL", _BlockedSMTP)
    mp.setattr(smtplib, "SMTP", _BlockedSMTP)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolate_contract_settings(tmp_path, monkeypatch):
    from core import contract_settings
    monkeypatch.setattr(contract_settings, "CONTRACT_SETTINGS_FILE", str(tmp_path / "contract_settings.json"))
