"""Одноразовая правка текста договора: конкретные слова заменяются на подстановки,
а название арендодателя, вид объекта, адрес и перечень имущества переносятся в «Данные объекта для договора» основного объекта.

Запуск на сервере:
  cd /app && .venv/bin/python tools/migrate_contract_template.py          (только показать, что изменится; ничего не записывается)
  cd /app && .venv/bin/python tools/migrate_contract_template.py --apply  (сделать резервную копию и записать изменения)
Откат: cp /data/contract_template.txt.backup_before_placeholders /data/contract_template.txt
"""
import json
import os
import re
import shutil
import sys

DATA_DIR = os.environ.get("CP_DATA_DIR", "/data")
TEMPLATE = f"{DATA_DIR}/contract_template.txt"
STATIC = "static/contract_template.txt"
SETTINGS = f"{DATA_DIR}/contract_settings.json"      # данные основного объекта (№1) лежат по прежнему пути
BACKUP = TEMPLATE + ".backup_before_placeholders"

OLD_ADDRESS = "г. Новосибирск, ул. Дачная, д.5, кв.286"
OLD_KIND = "квартира-студия"

REPLACEMENTS = [
    ("**Городская Пауза**, именуемый", "{{АРЕНДОДАТЕЛЬ}}, именуемый"),
    (f"пользование: {OLD_KIND}, расположенная по адресу {OLD_ADDRESS}", "пользование: {{ВИД_ОБЪЕКТА}} по адресу {{АДРЕС}}"),
    ("Арендодатель в лице Городская Пауза", "Арендодатель в лице {{АРЕНДОДАТЕЛЬ}}"),
    (f"помещения, находящуюся по адресу: {OLD_KIND}, расположенная по адресу {OLD_ADDRESS}", "помещения ({{ВИД_ОБЪЕКТА}}), находящуюся по адресу: {{АДРЕС}}"),
]


def main():
    apply = "--apply" in sys.argv
    src = TEMPLATE if os.path.exists(TEMPLATE) else STATIC
    if not os.path.exists(src):
        sys.exit("Не найден текст договора: " + TEMPLATE)
    text = open(src, encoding="utf-8").read()
    if "{{ИМУЩЕСТВО}}" in text:
        sys.exit("Договор уже содержит {{ИМУЩЕСТВО}}: правка уже была сделана, повторно не нужна.")

    problems = []
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count != 1:
            problems.append(f"фрагмент найден {count} раз(а), а нужен ровно 1: {old[:70]}…")
        text = text.replace(old, new)

    # перечень имущества: пронумерованные строки сразу после заголовка «Перечень имущества…»
    lines = text.split("\n")
    head = next((i for i, l in enumerate(lines) if "Перечень имущества" in l), None)
    inventory = []
    if head is None:
        problems.append("не найден заголовок «Перечень имущества»")
    else:
        i = head + 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        start = i
        while i < len(lines) and re.match(r"^\d+\.\s", lines[i]):
            inventory.append(lines[i].rstrip())
            i += 1
        if not inventory:
            problems.append("после заголовка не найден нумерованный список имущества")
        else:
            lines[start:i] = ["{{ИМУЩЕСТВО}}"]
    text = "\n".join(lines)

    print(f"Источник: {src}")
    print(f"Найдено позиций имущества: {len(inventory)}")
    for old, new in REPLACEMENTS:
        print(f"  заменяю: {old[:60]}…  →  {new[:60]}…")
    if problems:
        print("\nНЕ ПРИМЕНЯЮ, есть проблемы:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    settings = {}
    if os.path.exists(SETTINGS):
        try:
            settings = json.load(open(SETTINGS, encoding="utf-8"))
        except Exception:
            settings = {}
    for key, value in (("object_kind", OLD_KIND), ("address", OLD_ADDRESS), ("inventory", "\n".join(inventory))):
        if not str(settings.get(key) or "").strip():
            settings[key] = value
    settings.setdefault("landlord_name", "")

    if not apply:
        print("\nЭто пробный запуск, ничего не записано. Чтобы применить, добавьте --apply")
        return
    if os.path.exists(TEMPLATE):
        shutil.copy2(TEMPLATE, BACKUP)
    else:
        shutil.copy2(STATIC, BACKUP)
    open(TEMPLATE, "w", encoding="utf-8").write(text)
    json.dump(settings, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\nГотово. Резервная копия: {BACKUP}")
    print("Проверьте в админке: «Договор» → «Предпросмотр (PDF)».")


if __name__ == "__main__":
    main()
