"""Единое оформление кнопок: общие файлы buttons.css / buttons.js подключены ко всем страницам."""
import os

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
PAGES = ("index.html", "apartments.html", "discounts.html", "house_rules.html", "admin.html")


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def test_shared_button_files_exist_and_cover_all_button_kinds():
    css = read("buttons.css")
    for selector in (".btn-primary", ".btn-gold", ".btn-gold-w", ".btn-outline", ".btn-outline-s", ".btn-ghost", ".btn-danger", ".nav-btn", ".catalog-link", ".cal-nav"):
        assert selector in css, f"в buttons.css нет оформления для {selector}"
    assert "border-radius:999px" in css                                                   # форма «капсула»
    assert "prefers-reduced-motion" in css, "эффекты должны отключаться при «уменьшить анимацию»"
    js = read("buttons.js")
    assert "pointerdown" in js and "ripple" in js and "prefers-reduced-motion" in js


def test_every_page_loads_button_styles_after_its_own_styles():
    for page in PAGES:
        html = read(page)
        assert "/static/buttons.css" in html and "/static/buttons.js" in html, f"{page}: не подключены общие кнопки"
        # стили кнопок должны идти после собственных стилей страницы, иначе старый вид их перекроет
        own_styles_end = html.index("/static/admin.css") if page == "admin.html" else html.rfind("</style>")
        assert own_styles_end != -1 and own_styles_end < html.index("/static/buttons.css"), page


def test_catalog_main_button_uses_primary_style():
    assert "'btn btn-primary'" in read("apartments.html")
