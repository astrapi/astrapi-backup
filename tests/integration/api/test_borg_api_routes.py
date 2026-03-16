"""Integrationstests fuer Borg-API-Routen (FastAPI Router + TestClient)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.modules.borg.api as borg_api


@pytest.fixture
def borg_api_client():
    app = FastAPI()
    app.include_router(borg_api.router, prefix="/api/borg")
    return TestClient(app)


def test_create_route_speichert_form_payload_und_gibt_json_zurueck(borg_api_client, monkeypatch):
    captured = {}

    def fake_save_item(module, item_id, item):
        captured["module"] = module
        captured["item_id"] = item_id
        captured["item"] = item

    monkeypatch.setattr(borg_api, "next_item_id", lambda module: "9")
    monkeypatch.setattr(borg_api, "save_item", fake_save_item)

    response = borg_api_client.post(
        "/api/borg/create",
        data={
            "description": "Nightly Backup",
            "enabled": "on",
            "pre_0": "echo one",
            "pre_1": "echo two",
            "exclude_0": "/tmp",
        },
    )

    assert response.status_code == 200
    assert captured["module"] == "borg"
    assert captured["item_id"] == "9"
    assert captured["item"]["enabled"] is True
    assert captured["item"]["description"] == "Nightly Backup"
    assert captured["item"]["pre"] == ["echo one", "echo two"]
    assert captured["item"]["exclude"] == ["/tmp"]


def test_toggle_route_wechselt_enabled_und_gibt_status(borg_api_client, monkeypatch):
    cfg = {"1": {"enabled": False, "description": "Nightly"}}
    saved = {}

    monkeypatch.setattr(borg_api, "load_config", lambda module: cfg)

    def fake_save_item(module, item_id, item):
        saved["module"] = module
        saved["item_id"] = item_id
        saved["item"] = dict(item)

    monkeypatch.setattr(borg_api, "save_item", fake_save_item)

    response = borg_api_client.post("/api/borg/1/toggle")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["item"] == "1"
    assert body["enabled"] is True
    assert saved["module"] == "borg"
    assert saved["item_id"] == "1"
    assert saved["item"]["enabled"] is True
