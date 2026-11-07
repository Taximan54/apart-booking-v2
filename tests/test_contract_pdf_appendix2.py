"""Каждое «Приложение N …» в PDF договора начинается с новой страницы."""
import pytest

pypdf = pytest.importorskip("pypdf")

from core.contract_docs import generate_contract_pdf


def _pages(tmp_path, text):
    generate_contract_pdf(text, "T-APP", output_dir=str(tmp_path))
    reader = pypdf.PdfReader(str(tmp_path / "T-APP.pdf"))
    return [p.extract_text() for p in reader.pages]


def test_each_appendix_starts_new_page(tmp_path):
    text = (
        "1. Предмет\nТекст договора.\n\n"
        "**Приложение N 1**\nИмущество\n- стол\n\n"
        "Приложение N 2\nПамятка\nтекст\n"
    )
    pages = _pages(tmp_path, text)
    assert len(pages) == 3
    assert pages[1].lstrip().startswith("Приложение N 1")
    assert pages[2].lstrip().startswith("Приложение N 2")


def test_no_blank_page_when_text_starts_with_appendix(tmp_path):
    pages = _pages(tmp_path, "Приложение N 1\nтекст\n")
    assert len(pages) == 1
