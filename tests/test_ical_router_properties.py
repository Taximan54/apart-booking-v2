"""Календари площадок по объектам через API: админка выбирает объект, публичная ссылка отдаёт только его брони."""
from datetime import date, timedelta
import pytest
from fastapi import FastAPI

pytest.importorskip("httpx")
from fastapi.testclient import TestClient
import core.db as db, core.ical_sync as sync, core.properties as props
from core import bookings_repo as repo
from routers import ical as ri

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ICAL_FILE", str(tmp_path/"ical.json"))
    monkeypatch.setattr(props, "PROPERTIES_DIR", str(tmp_path/"properties"))
    reg = tmp_path/"properties.json"
    reg.write_text('[{"id":1,"name":"Основной","active":true,"slug":""},{"id":2,"name":"Дом у Оперного","active":false,"slug":"opera"}]', encoding="utf-8")
    monkeypatch.setattr(props, "PROPERTIES_FILE", str(reg))
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path/"b.db"))
    app = FastAPI(); app.include_router(ri.router)
    app.dependency_overrides[ri.require_admin] = lambda: True
    return TestClient(app)

def test_flow(client):
    # админка: выбран объект 2
    h2 = {"X-Property-Id": "2"}
    r = client.post("/api/admin/integrations/calendars", json={"name": "Авито", "source": "avito"}, headers=h2)
    assert r.status_code == 200 and [p["source"] for p in r.json()["platforms"]] == ["avito"]
    assert client.get("/api/admin/integrations/calendars").json()["platforms"] == []                 # у основного пусто
    assert len(client.get("/api/admin/integrations/calendars", headers=h2).json()["platforms"]) == 1
    assert client.get("/api/admin/integrations/calendars", headers={"X-Property-Id": "99"}).status_code == 404
    # основной
    r1 = client.post("/api/admin/integrations/calendars", json={"name": "Авито", "source": "avito"})
    url1 = r1.json()["platforms"][0]["export_url"]; url2 = client.get("/api/admin/integrations/calendars", headers=h2).json()["platforms"][0]["export_url"]
    assert url1 != url2
    # публичные календари: каждый только со своими бронями
    far = (date.today() + timedelta(days=400))
    repo.insert_block(1, "BLOCK-MAIN", far.isoformat(), (far+timedelta(days=2)).isoformat(), "x", 2)
    repo.insert_block(2, "BLOCK-SECOND", far.isoformat(), (far+timedelta(days=2)).isoformat(), "y", 2)
    path1 = "/ical/" + url1.rsplit("/ical/", 1)[1]; path2 = "/ical/" + url2.rsplit("/ical/", 1)[1]
    a, b = client.get(path1), client.get(path2)
    assert a.status_code == b.status_code == 200
    assert "BLOCK-MAIN" in a.text and "BLOCK-SECOND" not in a.text
    assert "BLOCK-SECOND" in b.text and "BLOCK-MAIN" not in b.text
    assert client.get("/ical/wrong.ics").status_code == 404
    # удаление площадки второго объекта не трогает первый
    d = client.delete("/api/admin/integrations/calendars/avito", headers=h2)
    assert d.status_code == 200 and d.json()["platforms"] == []
    assert client.get(path2).status_code == 404 and client.get(path1).status_code == 200
    assert len(client.get("/api/admin/integrations/calendars").json()["platforms"]) == 1

def test_direct_call_without_fastapi_uses_main(tmp_path, monkeypatch):
    import asyncio
    from core.models import CalendarPlatformCreate
    monkeypatch.setattr(sync, "ICAL_FILE", str(tmp_path/"ical.json"))
    monkeypatch.setattr(props, "PROPERTIES_FILE", str(tmp_path/"p.json"))
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path/"b.db"))
    out = asyncio.run(ri.add_calendar(CalendarPlatformCreate(name="Авито", source="avito"), True))
    assert [p["source"] for p in out["platforms"]] == ["avito"]
