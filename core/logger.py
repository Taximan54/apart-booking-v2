"""Единая настройка журнала (логов) приложения."""
import logging
import sys

_configured = False


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает логгер вида «citypause.<модуль>». Записи выводятся в стандартный
    вывод с датой, уровнем и именем модуля — их видно командой
    `journalctl -u apart` на сервере. Библиотечные логи (uvicorn, aiogram)
    эта настройка не затрагивает.
    """
    global _configured
    base = logging.getLogger("citypause")
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        base.addHandler(handler)
        base.setLevel(logging.INFO)
        base.propagate = False
        _configured = True
    return logging.getLogger("citypause." + name.rsplit(".", 1)[-1])
