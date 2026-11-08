"""Разовая правка шаблона согласия на ПД: почта арендодателя в пункте 8 становится подстановкой {{EMAIL_АРЕНДОДАТЕЛЯ}}.

Запуск на сервере:  cd /app && .venv/bin/python tools/migrate_consent_template.py
Перед правкой делается копия: /data/consent_template.txt.backup_before_placeholders
Повторный запуск безопасен: если подстановка уже есть, файл не трогается.
"""
import os
import shutil
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/data/consent_template.txt"
OLD = "citypause@mail.ru"
NEW = "{{EMAIL_АРЕНДОДАТЕЛЯ}}"
BACKUP = PATH + ".backup_before_placeholders"


def main():
    if not os.path.exists(PATH):
        print(f"Файл {PATH} не найден: шаблон, видимо, берётся из static/consent_template.txt. Ничего не изменено.")
        return 1
    with open(PATH, "r", encoding="utf-8") as f:
        text = f.read()
    if NEW in text:
        print("Подстановка уже есть. Ничего не изменено.")
        return 0
    if text.count(OLD) != 1:
        print(f"Ожидалась ровно одна почта {OLD}, найдено: {text.count(OLD)}. Ничего не изменено.")
        return 1
    if os.path.exists(BACKUP):
        print(f"Резервная копия уже есть ({BACKUP}), останавливаюсь, чтобы её не затереть. Ничего не изменено.")
        return 1
    shutil.copy2(PATH, BACKUP)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(text.replace(OLD, NEW))
    print(f"Готово. Копия: {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
