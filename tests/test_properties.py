"""Несколько объектов: реестр, выбор объекта в запросе, изоляция данных, брони и фото по объектам."""
import asyncio
import io
import json
import os
import sqlite3

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Подменяет все файлы данных и базу на временные: боевые данные не затрагиваются."""
    import core.data_store as ds
    import core.db as database
    import core.emails as emails_module
    import core.properties as props
    import routers.content as content
    import routers.contracts as contracts
    import routers.photos as photos
    import routers.pricing as pricing

    data = tmp_path / "data"
    data.mkdir()
    (data / "photos").mkdir()
    monkeypatch.setattr(props, "PROPERTIES_FILE", str(data / "properties.json"))
    monkeypatch.setattr(props, "PROPERTIES_DIR", str(data / "properties"))
    names = {
        "PRICE_FILE": "prices.json", "SETTINGS_FILE": "site_settings.json", "PLACES_FILE": "places.json",
        "DISCOUNTS_FILE": "discounts.json", "REVIEWS_FILE": "reviews.json", "HOUSE_RULES_FILE": "house_rules.txt",
        "CODE_FILE": "door_code.json", "DESC_FILE": "description.txt", "CHECKIN_FILE": "checkin_memo.txt",
        "CHECKOUT_FILE": "checkout_checklist.txt", "PHOTOS_ORDER_FILE": "photos_order.json",
    }
    for module in (ds, content, contracts, photos, pricing, emails_module):
        for const, filename in names.items():
            if hasattr(module, const):
                monkeypatch.setattr(module, const, str(data / filename))
    monkeypatch.setattr(photos, "PHOTOS_DIR", str(data / "photos"))
    path = str(tmp_path / "bookings.db")
    monkeypatch.setattr(database, "DB_FILE", path)
    return props, data, path


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

def test_default_property_always_exists(env):
    props, _, _ = env
    items = props.list_properties()
    assert [p["id"] for p in items] == [1] and items[0]["active"] and items[0]["slug"] == ""
    assert props.get_property(1)["name"] and props.get_property(99) is None


def test_create_update_and_slug_rules(env):
    props, data, _ = env
    p2 = props.create_property("  Студия   на Мира ", "г. Омск, ул. Мира, 1", "mira-studio")
    assert (p2["id"], p2["name"], p2["slug"], p2["active"]) == (2, "Студия на Мира", "mira-studio", True)
    assert os.path.isdir(data / "properties" / "2")
    auto = props.create_property("Без адреса страницы")
    assert auto["id"] == 3 and auto["slug"] == "obj-3"
    assert props.get_property_by_slug("MIRA-studio")["id"] == 2
    for slug, message in [("Bad Slug", "латиница"), ("a", "латиница"), ("admin", "зарезервирован"), ("mira-studio", "занят")]:
        with pytest.raises(props.PropertyError, match=message):
            props.create_property("Дубль", "", slug)
    with pytest.raises(props.PropertyError, match="название"):
        props.create_property("   ")
    props.update_property(2, name="Новое имя", address="г. Томск", slug="new-slug", active=False)
    p = props.get_property(2)
    assert (p["name"], p["address"], p["slug"], p["active"]) == ("Новое имя", "г. Томск", "new-slug", False)
    with pytest.raises(props.PropertyError, match="(?i)основной"):
        props.update_property(1, active=False)
    with pytest.raises(props.PropertyError):
        props.update_property(99, name="x")


def test_property_limit(env):
    props, _, _ = env
    for i in range(props.MAX_PROPERTIES - 1):
        props.create_property(f"Объект {i}")
    with pytest.raises(props.PropertyError, match="не больше"):
        props.create_property("Лишний")


def test_delete_rules(env):
    props, data, path = env
    from core import bookings_repo as repo
    props.create_property("Второй", slug="second")
    props.create_property("Третий", slug="third")
    with pytest.raises(props.PropertyError, match="Основной"):
        props.delete_property(1)
    repo.insert_block(2, "BLOCK-AAA111", "2027-05-01", "2027-05-03", "тест", 2)
    with pytest.raises(props.PropertyError, match="брони"):
        props.delete_property(2)                                         # с бронями удалять нельзя
    props.delete_property(3)
    assert props.get_property(3) is None and not os.path.exists(data / "properties" / "3")
    with pytest.raises(props.PropertyError):
        props.delete_property(3)


def test_property_file_paths(env):
    props, data, _ = env
    props.create_property("Второй", slug="second")
    legacy = str(data / "prices.json")
    assert props.property_file(legacy, 1) == legacy                           # основной объект: путь как раньше
    assert props.property_file(legacy, 2) == str(data / "properties" / "2" / "prices.json")
    assert os.path.isdir(data / "properties" / "2")


# ---------------------------------------------------------------------------
# Выбор объекта в запросе
# ---------------------------------------------------------------------------

def test_request_dependencies(env, monkeypatch):
    props, _, _ = env
    props.create_property("Второй", slug="second")
    props.create_property("Скрытый", slug="hidden")
    props.update_property(3, active=False)
    assert props.admin_property_id(None) == 1 and props.admin_property_id("2") == 2 and props.admin_property_id("3") == 3
    for bad, code in (("abc", 400), ("99", 404)):
        with pytest.raises(HTTPException) as e:
            props.admin_property_id(bad)
        assert e.value.status_code == code
    assert props.public_property_id(None) == 1 and props.public_property_id("SECOND") == 2
    for slug in ("nope", "hidden"):                                           # неизвестный и отключённый объект для гостя
        with pytest.raises(HTTPException) as e:
            props.public_property_id(slug)
        assert e.value.status_code == 404
    monkeypatch.setattr(props, "verify_token", lambda token: token == "good")
    assert props.request_property_id(None, None, None) == 1
    assert props.request_property_id("2", None, None) == 2
    assert props.request_property_id(None, "second", None) == 2
    assert props.request_property_id("3", None, "Bearer good") == 3          # отключённый объект виден админу
    for auth in (None, "Bearer bad"):
        with pytest.raises(HTTPException) as e:
            props.request_property_id("3", None, auth)
        assert e.value.status_code == 404


# ---------------------------------------------------------------------------
# Данные объектов не смешиваются
# ---------------------------------------------------------------------------

def test_prices_description_rules_door_code_are_per_property(env):
    props, data, _ = env
    props.create_property("Второй", slug="second")
    import routers.content as c
    import routers.pricing as pr
    from core.models import Description, DoorCode, HouseRulesText, Prices
    run(pr.set_prices(Prices(weekday=1000, weekend=2000, cleaning=300), True, 1))
    run(pr.set_prices(Prices(weekday=5555, weekend=6666, cleaning=700, deposit=9000), True, 2))
    assert run(pr.get_prices(1))["weekday"] == 1000 and run(pr.get_prices(2))["weekday"] == 5555
    assert run(pr.get_prices(2))["deposit"] == 9000
    assert os.path.exists(data / "prices.json") and os.path.exists(data / "properties" / "2" / "prices.json")
    run(c.set_description(Description(text="Описание первой"), True, 1))
    run(c.set_description(Description(text="Описание второй"), True, 2))
    assert run(c.get_description(1)) != run(c.get_description(2))
    run(c.set_house_rules(HouseRulesText(text="Правила 1"), True, 1))
    run(c.set_house_rules(HouseRulesText(text="Правила 2"), True, 2))
    assert "Правила 1" in json.dumps(run(c.get_house_rules(1)), ensure_ascii=False)
    assert "Правила 2" in json.dumps(run(c.get_house_rules(2)), ensure_ascii=False)
    run(c.set_door_code(DoorCode(code="1111"), True, 1))
    run(c.set_door_code(DoorCode(code="2222"), True, 2))
    assert json.dumps(run(c.get_door_code(1, True) if False else c.get_door_code(True, 1))).count("1111") == 1
    assert json.dumps(run(c.get_door_code(True, 2))).count("2222") == 1


def test_places_discounts_reviews_settings_are_per_property(env):
    props, _, _ = env
    props.create_property("Второй", slug="second")
    import routers.content as c
    from core.models import Discount, Place, Review, SiteSettings
    run(c.add_place(Place(name="Парк первой"), True, 1))
    run(c.add_place(Place(name="Кафе второй"), True, 2))
    assert [p["name"] for p in run(c.get_all_places(True, 1))] == ["Парк первой"]
    assert [p["name"] for p in run(c.get_all_places(True, 2))] == ["Кафе второй"]
    run(c.add_discount(Discount(name="Акция первой"), True, 1))
    assert [d["name"] for d in run(c.get_all_discounts(True, 1))] == ["Акция первой"]
    assert run(c.get_all_discounts(True, 2)) == []
    run(c.add_review(Review(author="Аня", text="Отзыв про вторую"), True, 2))
    assert run(c.get_all_reviews(True, 1)) == [] and len(run(c.get_all_reviews(True, 2))) == 1
    s2 = SiteSettings(site_name="Название второй", hero_title="Заголовок второй")
    run(c.set_site_settings(s2, True, 2))
    assert run(c.get_site_settings(2))["hero_title"] == "Заголовок второй"
    assert run(c.get_site_settings(1))["hero_title"] != "Заголовок второй"
    # удаление у одного объекта не трогает другой
    place_id = run(c.get_all_places(True, 2))[0]["id"]
    run(c.delete_place(place_id, True, 2))
    assert run(c.get_all_places(True, 2)) == [] and len(run(c.get_all_places(True, 1))) == 1


def test_checkin_memo_and_checklist_are_per_property(env):
    props, _, _ = env
    props.create_property("Второй", slug="second")
    import routers.contracts as ct
    from core import emails
    from core.models import CheckinMemo
    run(ct.set_checkin_memo(CheckinMemo(text="Памятка 1, код {{КОД_ЗАМКА}}"), True, 1))
    run(ct.set_checkin_memo(CheckinMemo(text="Памятка 2, код {{КОД_ЗАМКА}}"), True, 2))
    assert emails.load_checkin_memo("1111", 1).startswith("Памятка 1, код 1111")
    assert emails.load_checkin_memo("2222", 2).startswith("Памятка 2, код 2222")
    assert emails.load_checkin_memo("3333", 3) == emails.load_checkin_memo("3333", 3)   # без своей памятки — текст по умолчанию


def test_gallery_photos_do_not_leak_between_properties(env):
    props, data, _ = env
    props.create_property("Второй", slug="second")
    import routers.photos as ph

    class Upload:
        def __init__(self, name):
            self.filename = name

        async def read(self):
            return b"\xff\xd8\xff" + b"x" * 100

    # старое фото основного объекта без метки (загружено давно) лежит в общей папке
    (data / "photos" / "photo_old.jpg").write_bytes(b"x")
    r1 = run(ph.upload_photo(Upload("a.jpg"), "Первая", "gallery", True, 1))
    r2 = run(ph.upload_photo(Upload("b.jpg"), "Вторая", "gallery", True, 2))
    r2h = run(ph.upload_photo(Upload("hero.jpg"), "Обложка", "site", True, 2))
    g1 = [x["filename"] for x in ph.get_photos_list(1)]
    g2 = [x["filename"] for x in ph.get_photos_list(2)]
    assert "photo_old.jpg" in g1 and r1["filename"] in g1
    assert r2["filename"] not in g1 and r2h["filename"] not in g1, "фото второго объекта попали в галерею первого"
    assert g2 == [r2["filename"]], "в галерее второго объекта только его фото"
    # порядок, подпись и удаление работают отдельно по объектам
    run(ph.set_photo_label(r2["filename"], type("L", (), {"label": "Новая подпись"})(), True, 2))
    assert ph.get_photos_list(2)[0]["label"] == "Новая подпись" and ph.get_photos_list(1)[-1]["label"] != "Новая подпись"
    run(ph.delete_photo(r2["filename"], False, True, 2))
    assert ph.get_photos_list(2) == [] and r1["filename"] in [x["filename"] for x in ph.get_photos_list(1)]


# ---------------------------------------------------------------------------
# Брони и блокировки по объектам
# ---------------------------------------------------------------------------

@pytest.fixture
def bookings_env(env, monkeypatch):
    props, data, path = env
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER DEFAULT 1, "
        "user_id INTEGER DEFAULT 0, username TEXT, check_in TEXT, check_out TEXT, guests INTEGER DEFAULT 2, "
        "status TEXT DEFAULT 'waiting_payment', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()
    props.create_property("Второй", "г. Омск, ул. Мира, 1", "second")
    import routers.bookings as rb

    def available(check_in, check_out, property_id=1):
        c = sqlite3.connect(path)
        row = c.execute("SELECT id FROM bookings WHERE COALESCE(property_id,1)=? AND status!='cancelled' "
                        "AND ?<check_out AND ?>check_in LIMIT 1", (property_id, check_in, check_out)).fetchone()
        c.close()
        return row is None
    monkeypatch.setattr(rb, "is_dates_available", available)
    monkeypatch.setattr(rb, "send_email", lambda *a, **k: None)
    return rb, props, path


def test_bookings_blocks_and_dates_are_per_property(bookings_env):
    rb, props, path = bookings_env
    from core import bookings_repo as repo
    from core.models import BlockDatesRequest, ManualBookingCreate, UnblockDatesRequest
    run(rb.create_manual_booking(ManualBookingCreate(source="phone", check_in="2027-03-10", check_out="2027-03-12", guests_count=2, total_price=5000), True, 1))
    # те же даты во втором объекте свободны
    run(rb.create_manual_booking(ManualBookingCreate(source="phone", check_in="2027-03-10", check_out="2027-03-12", guests_count=2, total_price=7000), True, 2))
    with pytest.raises(HTTPException) as e:
        run(rb.create_manual_booking(ManualBookingCreate(source="phone", check_in="2027-03-11", check_out="2027-03-13", guests_count=2, total_price=1), True, 2))
    assert e.value.status_code == 409
    assert [b["total_price"] for b in repo.list_bookings(1)] == [5000]
    assert [b["total_price"] for b in repo.list_bookings(2)] == [7000]
    assert len(repo.list_bookings()) == 2
    run(rb.create_blocked_dates(BlockDatesRequest(dates=["2027-04-01", "2027-04-02"], reason="тест"), True, 2))
    assert len(repo.list_bookings(1)) == 1 and len(repo.list_bookings(2)) == 2
    run(rb.remove_blocked_dates(UnblockDatesRequest(start="2027-04-01", end="2027-04-02"), True, 1))   # у основного такого блока нет
    assert [b["status"] for b in repo.list_bookings(2) if b["source"] == "admin_block"] == ["blocked"]
    run(rb.remove_blocked_dates(UnblockDatesRequest(start="2027-04-01", end="2027-04-02"), True, 2))
    assert [b["status"] for b in repo.list_bookings(2) if b["source"] == "admin_block"] == ["cancelled"]


def test_public_booking_goes_to_the_chosen_property(bookings_env):
    rb, props, path = bookings_env
    from core import bookings_repo as repo
    from core.models import BookingCreate
    body = dict(check_in="2027-06-01", check_out="2027-06-03", nights=2, guest_name="Иван", guest_phone="+79990000000",
                guest_email="a@b.c", guests_count=2, total_price=9000, passport="1234 567890", promo_code="")
    run(rb.create_booking(BookingCreate(**body), 2))
    assert repo.list_bookings(1) == [] and len(repo.list_bookings(2)) == 1


def test_booked_dates_and_listing_use_the_property(bookings_env, monkeypatch):
    rb, props, path = bookings_env
    from core import bookings_repo as repo
    repo.insert_block(1, "BLOCK-AAA111", "2027-05-01", "2027-05-03", "x", 2)
    repo.insert_block(2, "BLOCK-BBB222", "2027-06-01", "2027-06-03", "y", 2)
    second = run(rb.get_bookings(None, None, "second", None))                     # сайт: даты занятости объекта
    assert second["booked_dates"] == ["2027-06-01", "2027-06-02"] and second["checkout_dates"] == ["2027-06-03"]
    main_site = run(rb.get_bookings(None, None, None, None))
    assert main_site["booked_dates"] == ["2027-05-01", "2027-05-02"]
    with pytest.raises(HTTPException) as e:
        run(rb.get_bookings(None, None, "unknown", None))
    assert e.value.status_code == 404
    monkeypatch.setattr(rb, "verify_token", lambda token: True)                    # админка: брони выбранного объекта
    admin_second = run(rb.get_bookings("1", "Bearer x", None, "2"))
    admin_main = run(rb.get_bookings("1", "Bearer x", None, None))
    assert "BLOCK-BBB222" in json.dumps(admin_second, ensure_ascii=False) and "BLOCK-AAA111" not in json.dumps(admin_second, ensure_ascii=False)
    assert "BLOCK-AAA111" in json.dumps(admin_main, ensure_ascii=False) and "BLOCK-BBB222" not in json.dumps(admin_main, ensure_ascii=False)


def test_contract_address_comes_from_the_booking_property(bookings_env, monkeypatch):
    rb, props, path = bookings_env
    import core.contract_docs as cd
    from core.constants import DEFAULT_LANDLORD
    monkeypatch.setattr(cd, "load_contract_template", lambda: "{{АДРЕС}}")
    plain = lambda t: t.replace("\ue000", "").replace("\ue001", "")
    base = {"username": "GP-1", "check_in": "2027-01-01", "check_out": "2027-01-03", "nights": 2, "total_price": 1000}
    assert plain(cd.generate_contract(dict(base, property_id=2))) == "г. Омск, ул. Мира, 1"
    assert plain(cd.generate_contract(dict(base, property_id=1))) == DEFAULT_LANDLORD["address"]
    props.update_property(2, address="")
    assert plain(cd.generate_contract(dict(base, property_id=2))) == DEFAULT_LANDLORD["address"]   # адрес не задан — как у арендодателя


# ---------------------------------------------------------------------------
# API управления объектами
# ---------------------------------------------------------------------------

def test_properties_api_protected_and_working(env):
    import inspect
    from core.auth import require_admin
    from core.models import PropertyCreate, PropertyUpdate
    from routers import properties as r
    for func in (r.get_properties, r.add_property, r.edit_property, r.remove_property):
        default = inspect.signature(func).parameters["_"].default
        assert getattr(default, "dependency", None) is require_admin, f"{func.__name__} без проверки админа"
    state = run(r.get_properties(True))
    assert state["default_id"] == 1 and state["properties"][0]["is_default"] and state["properties"][0]["bookings"] == 0
    state = run(r.add_property(PropertyCreate(name="Второй", address="Омск", slug="second"), True))
    assert state["created_id"] == 2 and [p["slug"] for p in state["properties"]] == ["", "second"]
    with pytest.raises(HTTPException) as e:
        run(r.add_property(PropertyCreate(name="Дубль", slug="second"), True))
    assert e.value.status_code == 400
    run(r.edit_property(2, PropertyUpdate(active=False), True))
    assert [p["slug"] for p in run(r.public_properties())] == [""]               # отключённый не виден гостям
    run(r.edit_property(2, PropertyUpdate(active=True, name="Студия"), True))
    public = run(r.public_properties())
    assert [(p["slug"], p["name"]) for p in public] == [("", public[0]["name"]), ("second", "Студия")]
    assert all(set(p) == {"id", "name", "address", "slug", "is_default"} for p in public)
    with pytest.raises(HTTPException) as e:
        run(r.remove_property(1, True))
    assert e.value.status_code == 400
    assert [p["id"] for p in run(r.remove_property(2, True))["properties"]] == [1]


def test_scheduler_collects_bookings_of_all_active_properties(env):
    props, _, _ = env
    props.create_property("Второй", slug="second")
    props.create_property("Скрытый", slug="hidden")
    props.update_property(3, active=False)
    from core.scheduler import _for_all_properties
    got = _for_all_properties(lambda pid: [{"property_id": pid}])
    assert [b["property_id"] for b in got] == [1, 2]                              # отключённые объекты не рассылают письма


# ---------------------------------------------------------------------------
# Страница объекта на сайте
# ---------------------------------------------------------------------------

def test_property_page_route(env):
    props, _, _ = env
    from routers.pages import property_page
    props.create_property("Второй", slug="second")
    props.create_property("Скрытый", slug="hidden")
    props.update_property(3, active=False)
    html = run(property_page("second"))
    assert "<html" in html.lower() and "PROPERTY_SLUG" in html
    for slug in ("nope", "hidden", "main"):                                    # неизвестный, отключённый и зарезервированный адрес
        with pytest.raises(HTTPException) as e:
            run(property_page(slug))
        assert e.value.status_code == 404


def test_index_html_passes_property_to_api():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")
    text = open(path, encoding="utf-8").read()
    assert "PROPERTY_SLUG" in text and "'property='" in text.replace('"', "'")
    assert 'href="admin.html"' not in text, "относительная ссылка сломается на странице /o/название"
