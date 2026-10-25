"""Каталог апартаментов (страница «Все апартаменты»): настройки, синхронизация с объектами, данные для гостей."""
import asyncio
import inspect
import os

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.run(coro)


PROPS = [
    {"id": 1, "name": "Городская Пауза", "address": "адрес", "active": True, "slug": ""},
    {"id": 2, "name": "Студия на Мира", "address": "", "active": True, "slug": "obj-2"},
    {"id": 3, "name": "Отключённая", "address": "", "active": False, "slug": "obj-3"},
]


@pytest.fixture
def cat(tmp_path, monkeypatch):
    import core.catalog as catalog
    monkeypatch.setattr(catalog, "CATALOG_FILE", str(tmp_path / "catalog.json"))
    state = {"props": [dict(p) for p in PROPS]}
    monkeypatch.setattr(catalog, "list_properties", lambda: state["props"])
    monkeypatch.setattr(catalog, "get_site_settings_dict", lambda pid=1: {"background_theme": "white", "color_theme": "emerald",
                        "amenities": [{"icon": "📶", "name": "Wi-Fi"}, {"icon": "", "name": "  "}, {"icon": "🅿", "name": "Парковка"}]})
    monkeypatch.setattr(catalog, "_own_site_name", lambda prop: "Дом у оперного" if prop["id"] == 1 else prop["name"])
    monkeypatch.setattr(catalog, "_photos", lambda pid, settings: [{"url": f"/data/photos/p{pid}.jpg", "label": ""}])
    monkeypatch.setattr(catalog, "_prices", lambda pid: {"weekday": 3500, "weekend": 4500})
    monkeypatch.setattr(catalog, "landlord_brand", lambda: "Городская Пауза")
    return catalog, state


def test_public_catalog_shows_only_active_objects_with_card_data(cat):
    catalog, _ = cat
    data = catalog.build_public_catalog()
    assert [i["id"] for i in data["items"]] == [1, 2] and data["count"] == 2           # отключённый объект не виден
    first = data["items"][0]
    assert first["name"] == "Дом у оперного" and first["url"] == "/" and first["price_from"] == 3500
    assert first["photos"] == [{"url": "/data/photos/p1.jpg", "label": ""}]
    assert "description" not in first                                                   # в карточке только подпись из админки
    assert [a["name"] for a in first["amenities"]] == ["Wi-Fi", "Парковка"]              # пустое удобство пропущено
    assert data["items"][1]["url"] == "/o/obj-2"
    assert data["brand"] == "Городская Пауза" and data["title"] == catalog.DEFAULT_TITLE and data["subtitle"] == catalog.DEFAULT_SUBTITLE
    assert (data["background_theme"], data["color_theme"]) == ("white", "emerald")      # как у основного сайта
    assert data["button_label"] == "Квартиры" and data["columns"] == "auto" and data["button_scale"] == 1.0
    assert data["fonts"]["brand_font"] == "cormorant" and data["fonts"]["text_font"] == "montserrat" and data["fonts"]["card_scale"] == 1.0


def test_saved_settings_order_visibility_and_texts(cat):
    catalog, _ = cat
    catalog.save_catalog_settings(" Сеть ", "Заголовок", "Подзаголовок", "black", "gold", [
        {"id": 2, "visible": True, "title": "Студия", "caption": "Центр", "site_url": "https://studio.example.ru"},
        {"id": 1, "visible": False, "title": "", "caption": "", "site_url": ""},
    ])
    data = catalog.build_public_catalog()
    assert [i["id"] for i in data["items"]] == [2]                                      # объект 1 скрыт в каталоге
    item = data["items"][0]
    assert (item["name"], item["caption"], item["url"]) == ("Студия", "Центр", "https://studio.example.ru")
    assert (data["brand"], data["title"], data["subtitle"], data["background_theme"], data["color_theme"]) == ("Сеть", "Заголовок", "Подзаголовок", "black", "gold")


def test_catalog_stays_in_sync_with_objects(cat):
    catalog, state = cat
    catalog.save_catalog_settings("", "", "", "", "", [{"id": 2}, {"id": 1}, {"id": 99, "caption": "удалён"}])
    assert [i["id"] for i in catalog.build_public_catalog()["items"]] == [2, 1]         # сохранённый порядок; несуществующий объект игнорируется
    state["props"].append({"id": 4, "name": "Новая", "address": "", "active": True, "slug": "obj-4"})
    assert [i["id"] for i in catalog.build_public_catalog()["items"]] == [2, 1, 4]      # новый объект появился сам, в конце
    state["props"][:] = [p for p in state["props"] if p["id"] != 2]
    assert [i["id"] for i in catalog.build_public_catalog()["items"]] == [1, 4]         # удалённый объект исчез
    admin = catalog.admin_catalog_state()
    assert [r["id"] for r in admin["items"]] == [1, 3, 4] and admin["items"][0]["is_default"] is True   # в админке видны и отключённые


def test_admin_state_includes_disabled_objects_and_defaults(cat):
    catalog, _ = cat
    admin = catalog.admin_catalog_state()
    assert [(r["id"], r["active"], r["visible"]) for r in admin["items"]] == [(1, True, True), (2, True, True), (3, False, True)]
    assert admin["defaults"]["title"] == catalog.DEFAULT_TITLE and admin["settings"]["title"] == ""


def test_validation(cat):
    catalog, _ = cat
    bad_calls = [
        dict(background_theme="neon"), dict(color_theme="rainbow"), dict(title="x" * 101), dict(subtitle="x" * 301), dict(brand="x" * 81),
        dict(items=[{"id": 1, "site_url": "javascript:alert(1)"}]), dict(items=[{"id": 1, "site_url": "https://a b.ru"}]),
        dict(items=[{"id": 1, "title": "x" * 81}]), dict(items=[{"id": 1, "caption": "x" * 201}]), dict(button_label="x" * 31), dict(columns="7"), dict(button_scale=3), dict(button_scale=0.1), dict(button_scale="большая"),
        dict(fonts={"brand_font": "comic_sans"}), dict(fonts={"title_scale": 3}), dict(fonts={"card_scale": 0.1}), dict(items=[{"id": 1, "site_url": "https://a.ru/" + "x" * 300}]),
    ]
    for kwargs in bad_calls:
        params = dict(brand="", title="", subtitle="", background_theme="", color_theme="", items=[])
        params.update(kwargs)
        with pytest.raises(catalog.CatalogError):
            catalog.save_catalog_settings(**params)
    assert not os.path.exists(catalog.CATALOG_FILE)                                      # при ошибке ничего не сохраняется
    catalog.save_catalog_settings("", "", "", "", "", [{"id": 1, "site_url": "/o/studio"}, {"id": 1, "caption": "дубль"}])
    assert [i["id"] for i in catalog.load_catalog_settings()["items"]] == [1]            # повтор объекта отбрасывается


def test_fonts_columns_and_button_label(cat):
    catalog, _ = cat
    catalog.save_catalog_settings("", "", "", "", "", [], button_label=" Все квартиры ", columns="3", button_scale=1.3, fonts={
        "brand_font": "pacifico", "brand_bold": True, "brand_scale": 1.5, "title_font": "poiret", "card_scale": 0.85, "text_font": "im_fell", "text_scale": 1.15})
    data = catalog.build_public_catalog()
    assert data["button_label"] == "Все квартиры" and data["columns"] == "3" and data["button_scale"] == 1.3
    f = data["fonts"]
    assert (f["brand_font"], f["brand_bold"], f["brand_scale"]) == ("pacifico", True, 1.5)
    assert f["title_font"] == "poiret" and f["subtitle_font"] == "montserrat"             # не заданный шрифт — по умолчанию
    assert f["card_scale"] == 0.85 and f["text_font"] == "im_fell" and f["text_scale"] == 1.15 and "text_bold" not in f
    admin = catalog.admin_catalog_state()
    assert admin["settings"]["fonts"]["brand_font"] == "pacifico" and admin["defaults"]["button_label"] == "Квартиры"
    # всё, что не поддерживает русский или неизвестно, при чтении заменяется значением по умолчанию
    import json
    saved = json.load(open(catalog.CATALOG_FILE, encoding="utf-8"))
    saved["fonts"]["brand_font"] = "great_vibes"
    saved["fonts"]["title_scale"] = 99
    saved["columns"] = "9"
    saved["button_scale"] = 50
    json.dump(saved, open(catalog.CATALOG_FILE, "w", encoding="utf-8"))
    data = catalog.build_public_catalog()
    assert data["fonts"]["brand_font"] == "cormorant" and data["fonts"]["title_scale"] == 1.0 and data["columns"] == "auto" and data["button_scale"] == 1.0


def test_caption_up_to_200_characters(cat):
    catalog, _ = cat
    caption = "Центр города, у оперного театра. " * 6
    catalog.save_catalog_settings("", "", "", "", "", [{"id": 1, "caption": caption[:200]}])
    assert catalog.build_public_catalog()["items"][0]["caption"] == caption[:200].strip()


def test_broken_settings_file_gives_defaults(cat):
    catalog, _ = cat
    open(catalog.CATALOG_FILE, "w", encoding="utf-8").write("{не json")
    assert catalog.load_catalog_settings()["items"] == []
    assert catalog.build_public_catalog()["count"] == 2


def test_price_from():
    import core.catalog as catalog
    assert catalog._price_from({"weekday": 3500, "weekend": 4500}) == 3500
    assert catalog._price_from({"weekday": 0, "weekend": 4000}) == 4000
    assert catalog._price_from({"weekday": "?", "weekend": None}) == 0


def test_old_properties_route_in_photos_router_is_gone():
    """Раньше routers/photos.py перекрывал список объектов старым адресом (отдавал список вместо {properties: …})."""
    from routers import photos
    assert all(getattr(r, "path", "") != "/api/admin/properties" for r in photos.router.routes)


def test_catalog_routes_and_page():
    from core.auth import require_admin
    from routers import pages, properties
    paths = {getattr(r, "path", "") for r in pages.router.routes}
    assert "/apartments" in paths and "/api/catalog" in paths
    for func in (properties.get_catalog_admin, properties.set_catalog_admin):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"
    page = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "apartments.html")
    text = open(page, encoding="utf-8").read()
    assert "/api/catalog" in text and "CP_THEME_NO_AUTO" in text
    assert "item.description" not in text                                                # в карточке нет описания


def test_admin_catalog_api(cat):
    from core.models import CatalogFonts, CatalogSettings, CatalogItemSettings
    from routers import properties
    catalog, _ = cat
    state = run(properties.set_catalog_admin(CatalogSettings(title="Наши квартиры", button_label="Все квартиры", button_scale=1.5, columns="2",
                fonts=CatalogFonts(title_font="poiret", title_scale=1.3, card_bold=True),
                items=[CatalogItemSettings(id=2, caption="Центр"), CatalogItemSettings(id=1)]), True))
    assert state["settings"]["title"] == "Наши квартиры" and [r["id"] for r in state["items"]][:2] == [2, 1]
    assert state["settings"]["button_label"] == "Все квартиры" and state["settings"]["columns"] == "2" and state["settings"]["button_scale"] == 1.5
    assert state["settings"]["fonts"]["title_font"] == "poiret" and state["settings"]["fonts"]["title_scale"] == 1.3 and state["settings"]["fonts"]["card_bold"] is True
    assert run(properties.get_catalog_admin(True))["items"][0]["caption"] == "Центр"
    with pytest.raises(HTTPException) as e:
        run(properties.set_catalog_admin(CatalogSettings(background_theme="neon"), True))
    assert e.value.status_code == 400
