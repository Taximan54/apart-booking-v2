"""/health/deep отвечает и на GET, и на HEAD (внешняя проверка UptimeRobot шлёт HEAD)."""
import pytest

pytest.importorskip("httpx")


def _client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import monitoring as router_mod

    m = router_mod.monitoring
    monkeypatch.setattr(m, "_check_db", lambda: [])
    monkeypatch.setattr(m, "_check_disk", lambda settings: [])
    monkeypatch.setattr(m, "load_settings", lambda: {})
    monkeypatch.setattr(m, "open_incident_count", lambda: 0)
    app = FastAPI()
    app.include_router(router_mod.router)
    return TestClient(app), m


def test_health_deep_get_and_head_ok(monkeypatch):
    client, _ = _client(monkeypatch)
    assert client.get("/health/deep").status_code == 200
    assert client.head("/health/deep").status_code == 200


def test_health_deep_head_reports_problem(monkeypatch):
    client, m = _client(monkeypatch)
    monkeypatch.setattr(m, "_check_db", lambda: ["db"])
    assert client.head("/health/deep").status_code == 503
