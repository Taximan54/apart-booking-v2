"""Статические страницы на месте и админка подключает свои CSS и JS."""
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def test_pages_exist():
    for name in ("index.html", "admin.html", "admin.css", "admin.js", "sign.html", "complete.html", "discounts.html"):
        assert os.path.exists(os.path.join(STATIC, name)), f"нет static/{name}"


def test_admin_links_existing_files():
    html = open(os.path.join(STATIC, "admin.html"), encoding="utf-8").read()
    for ref in re.findall(r'(?:href|src)="/static/(admin\.(?:css|js))(?:\?[^"]*)?"', html):
        assert os.path.exists(os.path.join(STATIC, ref))
    assert "/static/admin.css" in html and "/static/admin.js" in html
