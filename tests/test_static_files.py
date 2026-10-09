"""Статические страницы на месте и админка подключает свои CSS и JS."""
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def test_pages_exist():
    for name in ("index.html", "admin.html", "admin.css", "sign.html", "complete.html", "discounts.html"):
        assert os.path.exists(os.path.join(STATIC, name)), f"нет static/{name}"


def test_admin_links_existing_files():
    """admin.html подключает свои CSS и все части admin-js по порядку, init.js последним."""
    html = open(os.path.join(STATIC, "admin.html"), encoding="utf-8").read()
    assert os.path.exists(os.path.join(STATIC, "admin.css"))
    assert re.search(r'href="/static/admin\.css(\?[^"]*)?"', html)
    scripts = re.findall(r'<script src="/static/admin-js/([\w\-]+\.js)(?:\?[^"]*)?"></script>', html)
    assert scripts, "в admin.html не подключены файлы admin-js"
    assert scripts[0] == "core.js" and scripts[-1] == "init.js", f"неверный порядок загрузки: {scripts}"
    for name in scripts:
        assert os.path.exists(os.path.join(STATIC, "admin-js", name)), f"нет static/admin-js/{name}"
    assert len(scripts) == len(set(scripts)), "файл подключён дважды"
    assert "/static/admin.js" not in html, "старый единый admin.js больше не используется"


def test_admin_js_files_not_forgotten():
    """Каждый файл из папки admin-js подключён в admin.html (иначе его код не работает)."""
    html = open(os.path.join(STATIC, "admin.html"), encoding="utf-8").read()
    for name in os.listdir(os.path.join(STATIC, "admin-js")):
        if name.endswith(".js"):
            assert f"/static/admin-js/{name}" in html, f"{name} не подключён в admin.html"


def test_admin_js_syntax_if_node_available():
    """Проверка синтаксиса всех частей админки (если на машине есть Node.js)."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("Node.js не установлен")
    folder = os.path.join(STATIC, "admin-js")
    for name in sorted(os.listdir(folder)):
        if name.endswith(".js"):
            result = subprocess.run([node, "--check", os.path.join(folder, name)], capture_output=True, text=True)
            assert result.returncode == 0, f"{name}: {result.stderr[:300]}"
