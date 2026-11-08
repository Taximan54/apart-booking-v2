"""Настройка «Оформление админки» (admin_ui): по умолчанию «Как сейчас», ключ есть и в модели, и в настройках по умолчанию."""
from core.constants import DEFAULT_SETTINGS
from core.models import SiteSettings


def test_admin_ui_default_is_classic():
    assert DEFAULT_SETTINGS["admin_ui"] == "classic"
    assert SiteSettings().admin_ui == "classic"


def test_admin_ui_round_is_saved_and_old_settings_still_load():
    assert SiteSettings(admin_ui="round").admin_ui == "round"
    old = {k: v for k, v in DEFAULT_SETTINGS.items() if k != "admin_ui"}   # настройки, сохранённые до появления ключа
    assert SiteSettings(**old).admin_ui == "classic"
