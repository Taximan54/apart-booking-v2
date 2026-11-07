"""Общая настройка тестов: тесты не должны читать настоящие данные сервера.
Данные объекта для договора (/data/contract_settings.json) на время каждого теста подменяются пустым временным файлом."""
import pytest


@pytest.fixture(autouse=True)
def _isolate_contract_settings(tmp_path, monkeypatch):
    from core import contract_settings
    monkeypatch.setattr(contract_settings, "CONTRACT_SETTINGS_FILE", str(tmp_path / "contract_settings.json"))
