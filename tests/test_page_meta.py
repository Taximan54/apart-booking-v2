"""Название и описание сайта в <head> главной страницы подставляются из настроек."""
import core.page_meta as pm

PAGE = (
    '<head><title>Старое — Апартаменты посуточно</title>\n'
    '<meta property="og:url" content="https://old.example">\n'
    '<meta property="og:title" content="Старое">\n'
    '<meta property="og:description" content="Старое описание">\n'
    '<meta property="og:image" content="https://old.example/static/og-image.jpg">\n'
    '<meta name="description" content="Старое описание"></head><body>Городская Пауза</body>'
)


def _patch(monkeypatch, settings):
    import core.data_store as ds
    import core.landlord as ll
    monkeypatch.setattr(ds, "get_site_settings_dict", lambda property_id=1: settings)
    monkeypatch.setattr(ll, "site_url", lambda: "https://test.ru")


def test_meta_comes_from_settings(monkeypatch):
    _patch(monkeypatch, {"site_name": "Мой Дом", "hero_subtitle": "Уютные апартаменты"})
    out = pm.render_index_html(PAGE, 1, "/")
    assert "<title>Мой Дом — Апартаменты посуточно</title>" in out
    assert 'og:title" content="Мой Дом — Апартаменты посуточно"' in out
    assert 'og:url" content="https://test.ru"' in out
    assert 'og:image" content="https://test.ru/static/og-image.jpg"' in out
    assert out.count('content="Уютные апартаменты"') == 2
    assert "Старое" not in out and "old.example" not in out
    assert "<body>Городская Пауза</body>" in out   # тело страницы не трогаем


def test_property_page_url_and_escaping(monkeypatch):
    _patch(monkeypatch, {"site_name": 'Дом "у реки" <b>', "hero_subtitle": ""})
    out = pm.render_index_html(PAGE, 2, "/o/obj-2")
    assert 'og:url" content="https://test.ru/o/obj-2"' in out
    assert "&quot;у реки&quot; &lt;b&gt;" in out and "<b>" not in out.split("<body>")[0]
    assert 'content="Старое описание"' in out   # пустой подзаголовок: описание остаётся прежним


def test_errors_and_empty_name_leave_page_unchanged(monkeypatch):
    _patch(monkeypatch, {"site_name": "", "hero_subtitle": "x"})
    assert pm.render_index_html(PAGE) == PAGE
    import core.data_store as ds
    def boom(property_id=1):
        raise RuntimeError("нет настроек")
    monkeypatch.setattr(ds, "get_site_settings_dict", boom)
    assert pm.render_index_html(PAGE) == PAGE
