"""Breite API-Integrationstests fuer App- und Core-Module."""

import importlib

import pytest


APP_CRUD_MODULES = [
    "app.modules.borg.api",
    "app.modules.rsync.api",
    "app.modules.proxmox_hosts.api",
    "app.modules.proxmox_jobs.api",
    "app.modules.proxmox_lxc.api",
    "app.modules.remotes.api",
]


@pytest.mark.parametrize("module_path", APP_CRUD_MODULES)
def test_create_routes_work_for_all_app_crud_modules(api_client, monkeypatch, module_path):
    mod = importlib.import_module(module_path)
    saved = {}

    monkeypatch.setattr(mod, "next_item_id", lambda module: "9")
    monkeypatch.setattr(mod, "save_item", lambda module, item_id, item: saved.update(module=module, item_id=item_id, item=item))

    response = api_client.post(
        f"/api/{mod.KEY}/create",
        data={"description": f"{mod.KEY} item", "enabled": "on"},
    )

    assert response.status_code == 200
    assert saved["module"] == mod.KEY
    assert saved["item_id"] == "9"
    assert saved["item"]["description"] == f"{mod.KEY} item"
    assert saved["item"]["enabled"] is True


@pytest.mark.parametrize("module_path", APP_CRUD_MODULES)
def test_toggle_routes_work_for_all_app_crud_modules(api_client, monkeypatch, module_path):
    mod = importlib.import_module(module_path)
    cfg = {"1": {"enabled": False, "description": f"{mod.KEY} item"}}
    saved = {}

    monkeypatch.setattr(mod, "load_config", lambda module: cfg)
    monkeypatch.setattr(mod, "save_item", lambda module, item_id, item: saved.update(module=module, item_id=item_id, item=dict(item)))

    response = api_client.post(f"/api/{mod.KEY}/1/toggle")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert saved["module"] == mod.KEY
    assert saved["item"]["enabled"] is True


@pytest.mark.parametrize("module_path", APP_CRUD_MODULES)
def test_delete_routes_work_for_all_app_crud_modules(api_client, monkeypatch, module_path):
    mod = importlib.import_module(module_path)
    monkeypatch.setattr(mod, "delete_item", lambda module, item_id: True)

    response = api_client.request("DELETE", f"/api/{mod.KEY}/1/delete")

    assert response.status_code in {200, 204}


def test_borg_preview_route_renders_modal(api_client, monkeypatch):
    borg_api = importlib.import_module("app.modules.borg.api")
    monkeypatch.setattr(borg_api, "get_item", lambda module, item_id: {"description": "Nightly Borg"})
    monkeypatch.setattr(
        borg_api,
        "_preview_borg",
        lambda item_id: [{"label": "create", "cmd": "borg create ::archive /data"}],
    )

    response = api_client.get("/api/borg/1/preview")

    assert response.status_code == 200
    assert "Nightly Borg" in response.text
    assert "borg create" in response.text


def test_remotes_wake_and_shutdown_routes(api_client, monkeypatch):
    remotes_api = importlib.import_module("app.modules.remotes.api")
    monkeypatch.setattr(remotes_api, "get_item", lambda module, item_id: {"mac": "AA:BB:CC:DD:EE:FF", "host": "backup-host", "ssh_user": "root"})
    monkeypatch.setattr(remotes_api.subprocess, "run", lambda *args, **kwargs: None)

    wake_response = api_client.post("/api/remotes/1/wake")
    shutdown_response = api_client.post("/api/remotes/1/shutdown")

    assert wake_response.status_code == 200
    assert wake_response.json()["mac"] == "AA:BB:CC:DD:EE:FF"
    assert shutdown_response.status_code == 200
    assert shutdown_response.json()["host"] == "backup-host"


def test_history_and_errors_api_routes_render_html(api_client, monkeypatch):
    monkeypatch.setattr(
        "api.storage.list_history",
        lambda limit=200, module=None: [{
            "started_at": "2026-03-16 08:00",
            "module": "borg",
            "description": "Nightly Backup",
            "item_id": "1",
            "mode": "run",
            "duration_s": 62,
            "status": "ok",
        }],
    )
    monkeypatch.setattr(
        "helpers.logger.get_all_errors",
        lambda *args, **kwargs: [{
            "date": "2026-03-16",
            "time": "08:00",
            "module": "borg",
            "description": "Disk full",
            "item_id": "1",
            "lines": ["ERROR: Disk full"],
        }],
    )

    history_tab = api_client.get("/api/history/tab")
    history_rows = api_client.get("/api/history/rows")
    errors = api_client.get("/api/errors")

    assert history_tab.status_code == 200
    assert history_rows.status_code == 200
    assert errors.status_code == 200
    assert "borg" in history_tab.text
    assert "Disk full" in errors.text


def test_sysinfo_api_routes_return_expected_sections(api_client, monkeypatch):
    sysinfo_api = importlib.import_module("core.modules.sysinfo.api")
    monkeypatch.setattr(sysinfo_api, "collect", lambda: {"hostname": "backupctl-host"})
    monkeypatch.setattr(sysinfo_api, "collect_cached", lambda: {"cpu": {"percent": 12}, "mem": {"percent": 42}, "disks": [{"mount": "/data"}]})

    root = api_client.get("/api/sysinfo/")
    cpu = api_client.get("/api/sysinfo/cpu")
    ram = api_client.get("/api/sysinfo/ram")
    disk = api_client.get("/api/sysinfo/disk")

    assert root.status_code == 200
    assert root.json()["hostname"] == "backupctl-host"
    assert cpu.json()["percent"] == 12
    assert ram.json()["percent"] == 42
    assert disk.json()[0]["mount"] == "/data"


def test_notify_channel_api_routes(api_client, monkeypatch):
    notify_api = importlib.import_module("core.modules.notify.api")
    notify_engine = importlib.import_module("core.modules.notify.engine")
    monkeypatch.setattr(notify_api.store, "list", lambda: {"ch-1": {"label": "Ops Channel", "backend": "ntfy", "enabled": True}})
    monkeypatch.setattr(notify_api.store, "get", lambda channel_id: {"label": "Ops Channel", "backend": "ntfy", "enabled": True})
    monkeypatch.setattr(notify_api.store, "create", lambda channel_id, item: item)
    monkeypatch.setattr(notify_api.store, "update", lambda channel_id, item: item)
    monkeypatch.setattr(notify_api.store, "toggle", lambda channel_id, default=False: True)
    monkeypatch.setattr(notify_api.store, "delete", lambda channel_id: None)
    monkeypatch.setattr(notify_engine, "test_channel", lambda channel_id: (True, "sent"))

    create_payload = {
        "label": "Ops Channel",
        "backend": "ntfy",
        "enabled": True,
        "ntfy_url": "https://ntfy.sh",
        "ntfy_topic": "ops",
        "ntfy_token": "",
        "mail_smtp_host": "",
        "mail_smtp_port": 587,
        "mail_smtp_user": "",
        "mail_smtp_password": "",
        "mail_smtp_tls": True,
        "mail_from": "",
        "mail_to": "",
        "mail_subject_prefix": "[Notify]",
    }

    assert api_client.get("/api/notify/").status_code == 200
    assert api_client.get("/api/notify/ch-1").status_code == 200
    assert api_client.post("/api/notify/?channel_id=ch-2", json=create_payload).status_code == 201
    assert api_client.put("/api/notify/ch-1", json=create_payload).status_code == 200
    assert api_client.patch("/api/notify/ch-1/toggle").json()["enabled"] is True
    assert api_client.post("/api/notify/ch-1/test").json()["ok"] is True
    assert api_client.request("DELETE", "/api/notify/ch-1").status_code == 204


def test_notify_job_api_routes(api_client, monkeypatch):
    notify_api = importlib.import_module("core.modules.notify.api")
    notify_engine = importlib.import_module("core.modules.notify.engine")
    monkeypatch.setattr(notify_api.job_store, "list", lambda: {"job-1": {"label": "Error Alerts", "channel_id": "ch-1", "enabled": True, "events": ["error"], "sources": ["borg"]}})
    monkeypatch.setattr(notify_api.job_store, "get", lambda job_id: {"label": "Error Alerts", "channel_id": "ch-1", "enabled": True, "events": ["error"], "sources": ["borg"]})
    monkeypatch.setattr(notify_api.job_store, "create", lambda job_id, item: item)
    monkeypatch.setattr(notify_api.job_store, "update", lambda job_id, item: item)
    monkeypatch.setattr(notify_api.job_store, "toggle", lambda job_id, default=False: True)
    monkeypatch.setattr(notify_api.job_store, "delete", lambda job_id: None)
    monkeypatch.setattr(notify_engine, "test_job", lambda job_id: (True, "sent"))

    create_payload = {
        "label": "Error Alerts",
        "channel_id": "ch-1",
        "enabled": True,
        "events": ["error"],
        "sources": ["borg"],
    }

    assert api_client.get("/api/notify/jobs/").status_code == 200
    assert api_client.get("/api/notify/jobs/job-1").status_code == 200
    assert api_client.post("/api/notify/jobs/?job_id=job-2", json=create_payload).status_code == 201
    assert api_client.put("/api/notify/jobs/job-1", json=create_payload).status_code == 200
    assert api_client.patch("/api/notify/jobs/job-1/toggle").json()["enabled"] is True
    assert api_client.post("/api/notify/jobs/job-1/test").json()["ok"] is True
    assert api_client.request("DELETE", "/api/notify/jobs/job-1").status_code == 204


def test_scheduler_api_routes(api_client, monkeypatch):
    scheduler_engine = importlib.import_module("core.modules.scheduler.engine")
    monkeypatch.setattr(scheduler_engine, "list_jobs", lambda: [{"id": "nightly", "label": "Nightly Sync", "enabled": True, "cron": "0 2 * * *", "steps": ["borg.run"]}])
    monkeypatch.setattr(scheduler_engine, "get_registered_actions", lambda: {"borg.run": "Borg Run"})
    monkeypatch.setattr(scheduler_engine, "get_job", lambda job_id: {"id": job_id, "label": "Nightly Sync", "enabled": True, "cron": "0 2 * * *", "steps": ["borg.run"], "notify_start": True, "notify_end": True})
    monkeypatch.setattr(scheduler_engine, "create_job", lambda *args, **kwargs: {"id": args[0], "label": args[1]})
    monkeypatch.setattr(scheduler_engine, "update_job", lambda *args, **kwargs: {"id": args[0], "label": args[1]})
    monkeypatch.setattr(scheduler_engine, "delete_job", lambda job_id: None)
    monkeypatch.setattr(scheduler_engine, "trigger_job", lambda job_id: None)
    monkeypatch.setattr(scheduler_engine, "toggle_job", lambda job_id: None)

    payload = {
        "label": "Nightly Sync",
        "cron": "0 2 * * *",
        "enabled": True,
        "steps": ["borg.run"],
        "notify_start": True,
        "notify_end": True,
    }

    assert api_client.get("/api/scheduler/").status_code == 200
    assert api_client.get("/api/scheduler/actions").status_code == 200
    assert api_client.get("/api/scheduler/nightly").status_code == 200
    assert api_client.post("/api/scheduler/nightly", json=payload).status_code == 201
    assert api_client.put("/api/scheduler/nightly", json=payload).status_code == 200
    assert api_client.patch("/api/scheduler/nightly/toggle").status_code == 200
    assert api_client.post("/api/scheduler/nightly/trigger").json()["ok"] is True
    assert api_client.request("DELETE", "/api/scheduler/nightly").status_code == 204