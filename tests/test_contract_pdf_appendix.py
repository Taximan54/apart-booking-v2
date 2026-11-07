"""Приложения к договору: список имущества не должен печататься крупным шрифтом заголовков,
даже если строка «Приложение N 1» оформлена жирным и по центру (**…** и [[CENTER]])."""
from core import contract_docs as cd


def _styles(monkeypatch, tmp_path, text):
    log = []
    original = cd.Paragraph

    class Logging(original):
        def __init__(self, text, style, *a, **k):
            log.append((text, style.name))
            super().__init__(text, style, *a, **k)

    monkeypatch.setattr(cd, "Paragraph", Logging)
    cd.generate_contract_pdf(text, "t", output_dir=str(tmp_path))
    return log


TEXT = """**1. Предмет Договора**
1.1. Текст договора

[[CENTER]]**Приложение N 1**[[/CENTER]]
[[CENTER]]**Перечень имущества**[[/CENTER]]

1. Кухонный гарнитур
2. Телевизор
3. Панель видеодомофона

[[CENTER]]**Приложение N 2**[[/CENTER]]
Мы, нижеподписавшиеся"""


def test_inventory_after_bold_centered_appendix_header_is_normal_size(monkeypatch, tmp_path):
    log = _styles(monkeypatch, tmp_path, TEXT)
    items = [style for text, style in log if text.startswith(("1. ", "2. ", "3. "))]
    assert len(items) == 3
    assert items == ["contract", "contract", "contract"]


def test_plain_marked_strips_bold_markers():
    assert cd._plain_marked("**Приложение N 1**") == "Приложение N 1"
    assert cd._plain_marked(cd._AUTO_BOLD_OPEN + "Приложение" + cd._AUTO_BOLD_CLOSE).startswith("Приложение")
