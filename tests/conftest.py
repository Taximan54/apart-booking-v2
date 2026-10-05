"""Общая настройка тестов: корень проекта в путь импорта и рабочая папка."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)  # main.py монтирует папку static относительно текущей папки
