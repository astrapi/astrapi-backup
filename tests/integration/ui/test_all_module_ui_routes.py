"""Breite UI-Integrationstests fuer App- und Core-Module."""

import importlib

import pytest


@pytest.mark.parametrize(
    ("path", "expected_text", "setup"),
    [
        ("/ui/borg/content", "Nightly Borg", "crud"),
        ("/ui/rsync/content", "Nightly Rsync", "crud"),
        ("/ui/proxmox_hosts/content", "PBS Host", "crud"),
        ("/ui/proxmox_jobs/content", "PBS Job", "crud"),
        ("/ui/proxmox_lxc/content", "Container 101", "crud"),
        ("/ui/remotes/content", "Remote Node", "remotes"),
        ("/ui/history/content", "Nightly Backup", "history"),
        ("/ui/errors/content", "Disk full", "errors"),
        ("/ui/notify/content", "Main Channel", "notify"),
        ("/ui/scheduler/content", "Nightly Sync", "scheduler"),
        ("/ui/settings/content", "TIMEZONE", "settings"),
        ("/ui/sysinfo/content", "backupctl-host", "sysinfo"),
        ("/ui/sysinfo/metrics", "backupctl-host", "sysinfo"),
    ],
)
def test_content_routes_render_for_all_modules(flask_ui_client, monkeypatch, path, expected_text, setup):
    if setup == "crud":
        monkeypatch.setattr(
            "api.storage.load_config",
            lambda module: {"1": {"description": expected_text, "enabled": True}},
        )
        monkeypatch.setattr("api.routers.run.get_running", lambda: {})
    elif setup == "remotes":
        monkeypatch.setattr(
            "api.storage.load_config",
            lambda module: {"1": {"description": expected_text, "enabled": True}},
        )
    elif setup == "history":
        monkeypatch.setattr(
            "api.storage.list_history",
            lambda limit=200, module=None: [{
                "started_at": "2026-03-16 08:00",
                "module": "borg",
                "description": expected_text,
                "item_id": "1",
                "mode": "run",
                "duration_s": 61,
                "status": "ok",
            }],
        )
    elif setup == "errors":
        monkeypatch.setattr(
            "helpers.logger.get_all_errors",
            lambda *args, **kwargs: [{
                "date": "2026-03-16",
                "time": "08:00",
                "module": "borg",
                "description": expected_text,
                "item_id": "1",
                "lines": [f"ERROR: {expected_text}"],
            }],
        )
    elif setup == "notify":
        notify_storage = importlib.import_module("core.modules.notify.storage")
        monkeypatch.setattr(notify_storage.store, "list", lambda: {"ch-1": {"label": expected_text, "backend": "ntfy", "enabled": True}})
        monkeypatch.setattr(notify_storage.job_store, "list", lambda: {"job-1": {"label": "Alert Job", "enabled": True}})
    elif setup == "scheduler":
        scheduler_engine = importlib.import_module("core.modules.scheduler.engine")
        monkeypatch.setattr(scheduler_engine, "list_jobs", lambda: [{"id": "nightly", "label": expected_text, "enabled": True, "cron": "0 2 * * *", "steps": []}])
        monkeypatch.setattr(scheduler_engine, "get_registered_actions", lambda: {"borg.run": "Borg Run"})
    elif setup == "settings":
        monkeypatch.setattr("core.ui.settings_registry.all_settings", lambda: {"TIMEZONE": "Europe/Berlin", "LIGHT_MODE": "0"})
    elif setup == "sysinfo":
        sysinfo_ui = importlib.import_module("core.modules.sysinfo.ui")
        monkeypatch.setattr(
            sysinfo_ui,
            "collect",
            lambda: {
                "ok": True,
                "error": "",
                "collected_at": "2026-03-16 08:00",
                "cpu": {"percent": 5, "cores": 8, "freq": "3.2 GHz", "model": "Test CPU"},
                "mem": {"percent": 15, "used": "2 GB", "free": "14 GB", "total": "16 GB"},
                "swap": {"percent": 0, "used": "0 GB", "total": "2 GB"},
                "disks": [{"mountpoint": "/data", "device": "/dev/sda1", "fstype": "ext4", "used_fmt": "10 GB", "total_fmt": "100 GB", "percent": 10}],
                "software": {"Python": "3.14", "BackupCtl": "26.3.1"},
                "services": [],
                "system": {"hostname": expected_text, "kernel": "6.8", "os_name": "Linux", "sys_uptime": "1d", "app_uptime": "2h"},
                "interfaces": [{"name": "eth0", "up": True, "speed": "1 Gbit", "ipv4": ["192.168.1.10"], "ipv6": []}],
            },
        )

    response = flask_ui_client.get(path)

    assert response.status_code == 200
    assert expected_text in response.get_data(as_text=True)


@pytest.mark.parametrize("module_key", ["borg", "rsync", "proxmox_hosts", "proxmox_jobs", "proxmox_lxc", "remotes"])
def test_create_modals_render_for_all_crud_modules(flask_ui_client, module_key):
    response = flask_ui_client.get(f"/ui/{module_key}/create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "create-edit-modal" in html
    assert f"/api/{module_key}/create" in html


@pytest.mark.parametrize("module_key", ["borg", "rsync", "proxmox_hosts", "proxmox_jobs", "proxmox_lxc", "remotes"])
def test_edit_modals_render_for_all_crud_modules(flask_ui_client, monkeypatch, module_key):
    monkeypatch.setattr(
        "api.storage.get_item",
        lambda module, item: {"description": f"{module_key} item", "enabled": True, "pre": [], "post": [], "exclude": []},
    )

    response = flask_ui_client.get(f"/ui/{module_key}/42/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "create-edit-modal" in html
    assert f"/api/{module_key}/42/edit" in html


@pytest.mark.parametrize(
    ("path", "confirm_url"),
    [
        ("/ui/borg/42/toggle?enabled=True&description=Nightly", "/api/borg/42/toggle"),
        ("/ui/borg/42/delete?description=Nightly", "/api/borg/42/delete"),
        ("/ui/rsync/42/toggle?enabled=True&description=Nightly", "/api/rsync/42/toggle"),
        ("/ui/rsync/42/delete?description=Nightly", "/api/rsync/42/delete"),
        ("/ui/proxmox_hosts/42/toggle?enabled=True&description=PBS", "/api/proxmox_hosts/42/toggle"),
        ("/ui/proxmox_hosts/42/delete?description=PBS", "/api/proxmox_hosts/42/delete"),
        ("/ui/proxmox_jobs/42/toggle?enabled=True&description=Job", "/api/proxmox_jobs/42/toggle"),
        ("/ui/proxmox_jobs/42/delete?description=Job", "/api/proxmox_jobs/42/delete"),
        ("/ui/proxmox_lxc/42/toggle?enabled=True&description=CT", "/api/proxmox_lxc/42/toggle"),
        ("/ui/proxmox_lxc/42/delete?description=CT", "/api/proxmox_lxc/42/delete"),
        ("/ui/remotes/42/toggle?enabled=True&description=Remote", "/api/remotes/42/toggle"),
        ("/ui/remotes/42/delete?description=Remote", "/api/remotes/42/delete"),
        ("/ui/remotes/42/wake?description=Remote", "/api/remotes/42/wake"),
        ("/ui/remotes/42/shutdown?description=Remote", "/api/remotes/42/shutdown"),
    ],
)
def test_confirm_modals_render_for_all_supported_actions(flask_ui_client, path, confirm_url):
    response = flask_ui_client.get(path)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert confirm_url in html
    assert "ds-modal-backdrop" in html


def test_notify_channel_modals_render(flask_ui_client, monkeypatch):
    notify_storage = importlib.import_module("core.modules.notify.storage")
    monkeypatch.setattr(notify_storage.store, "get", lambda channel_id: {"label": "Ops Channel", "backend": "ntfy", "enabled": True, "ntfy_topic": "ops"})

    backend_select = flask_ui_client.get("/ui/notify/backend-select")
    create_modal = flask_ui_client.get("/ui/notify/create/ntfy")
    edit_modal = flask_ui_client.get("/ui/notify/ch-1/edit")
    delete_modal = flask_ui_client.get("/ui/notify/ch-1/delete")
    toggle_modal = flask_ui_client.get("/ui/notify/ch-1/toggle?enabled=True")

    assert backend_select.status_code == 200
    assert "ntfy" in backend_select.get_data(as_text=True)
    assert "channel-modal" in create_modal.get_data(as_text=True)
    assert "Ops Channel" in edit_modal.get_data(as_text=True)
    assert "/api/notify/ch-1" in delete_modal.get_data(as_text=True)
    assert "/api/notify/ch-1/toggle" in toggle_modal.get_data(as_text=True)


def test_notify_job_modals_render(flask_ui_client, monkeypatch):
    notify_storage = importlib.import_module("core.modules.notify.storage")
    notify_ui = importlib.import_module("core.modules.notify.ui")
    scheduler_engine = importlib.import_module("core.modules.scheduler.engine")
    monkeypatch.setattr(notify_storage.store, "list", lambda: {"ch-1": {"label": "Ops Channel", "backend": "ntfy", "enabled": True}})
    monkeypatch.setattr(notify_storage.job_store, "get", lambda job_id: {"label": "Error Alerts", "channel_id": "ch-1", "events": ["error"], "sources": ["borg"], "enabled": True})
    monkeypatch.setattr(notify_ui, "get_registered_sources", lambda: {"borg": "Borg", "nightly": "Nightly"})
    monkeypatch.setattr(scheduler_engine, "list_jobs", lambda: [{"id": "nightly", "label": "Nightly"}])

    create_modal = flask_ui_client.get("/ui/notify/jobs/create")
    edit_modal = flask_ui_client.get("/ui/notify/jobs/job-1/edit")
    delete_modal = flask_ui_client.get("/ui/notify/jobs/job-1/delete")
    toggle_modal = flask_ui_client.get("/ui/notify/jobs/job-1/toggle?enabled=True")

    assert create_modal.status_code == 200
    assert "job-modal" in create_modal.get_data(as_text=True)
    assert "Error Alerts" in edit_modal.get_data(as_text=True)
    assert "/api/notify/jobs/job-1" in delete_modal.get_data(as_text=True)
    assert "/api/notify/jobs/job-1/toggle" in toggle_modal.get_data(as_text=True)


def test_scheduler_modals_render(flask_ui_client, monkeypatch):
    scheduler_engine = importlib.import_module("core.modules.scheduler.engine")
    monkeypatch.setattr(scheduler_engine, "get_registered_actions", lambda: {"borg.run": "Borg Run"})
    monkeypatch.setattr(scheduler_engine, "get_job", lambda job_id: {"id": job_id, "label": "Nightly Sync", "cron": "0 2 * * *", "enabled": True, "steps": ["borg.run"], "notify_start": True, "notify_end": True})

    new_modal = flask_ui_client.get("/ui/scheduler/job/new")
    edit_modal = flask_ui_client.get("/ui/scheduler/job/nightly/edit")
    delete_modal = flask_ui_client.get("/ui/scheduler/job/nightly/delete")
    toggle_modal = flask_ui_client.get("/ui/scheduler/job/nightly/toggle?enabled=True")

    assert new_modal.status_code == 200
    assert "scheduler-job-modal" in new_modal.get_data(as_text=True)
    assert "Nightly Sync" in edit_modal.get_data(as_text=True)
    assert "/api/scheduler/nightly" in delete_modal.get_data(as_text=True)
    assert "/api/scheduler/nightly/toggle" in toggle_modal.get_data(as_text=True)


def test_notify_form_actions_render_updated_list(flask_ui_client, monkeypatch):
    notify_storage = importlib.import_module("core.modules.notify.storage")
    monkeypatch.setattr(notify_storage.store, "create", lambda channel_id, data: data)
    monkeypatch.setattr(notify_storage.store, "update", lambda channel_id, data: data)
    monkeypatch.setattr(notify_storage.store, "list", lambda: {"ch-1": {"label": "Ops Channel", "backend": "ntfy", "enabled": True}})
    monkeypatch.setattr(notify_storage.job_store, "list", lambda: {})

    create_response = flask_ui_client.post("/ui/notify/", data={"label": "Ops Channel", "backend": "ntfy", "ntfy_url": "https://ntfy.sh", "ntfy_topic": "ops", "enabled": "1"})
    edit_response = flask_ui_client.post("/ui/notify/ch-1/update", data={"label": "Ops Channel", "backend": "ntfy", "ntfy_url": "https://ntfy.sh", "ntfy_topic": "ops", "enabled": "1"})

    assert create_response.status_code == 200
    assert edit_response.status_code == 200
    assert "Ops Channel" in create_response.get_data(as_text=True)
    assert "Ops Channel" in edit_response.get_data(as_text=True)


def test_scheduler_form_actions_handle_validation_and_success(flask_ui_client, monkeypatch):
    scheduler_engine = importlib.import_module("core.modules.scheduler.engine")
    monkeypatch.setattr(scheduler_engine, "get_registered_actions", lambda: {"borg.run": "Borg Run"})
    monkeypatch.setattr(scheduler_engine, "list_jobs", lambda: [{"id": "nightly", "label": "Nightly Sync", "enabled": True, "cron": "0 2 * * *", "steps": ["borg.run"]}])
    monkeypatch.setattr(scheduler_engine, "create_job", lambda *args, **kwargs: {"id": args[0]})
    monkeypatch.setattr(scheduler_engine, "update_job", lambda *args, **kwargs: {"id": args[0]})
    monkeypatch.setattr(scheduler_engine, "get_job", lambda job_id: {"id": job_id, "label": "Nightly Sync", "cron": "0 2 * * *", "enabled": True, "steps": ["borg.run"], "notify_start": True, "notify_end": True})
    monkeypatch.setattr(scheduler_engine, "trigger_job", lambda job_id: None)

    invalid = flask_ui_client.post("/ui/scheduler/job", data={"job_id": "", "label": "", "cron": ""})
    create_ok = flask_ui_client.post("/ui/scheduler/job", data={"job_id": "nightly", "label": "Nightly Sync", "cron": "0 2 * * *", "enabled": "1", "steps": ["borg.run"], "notify_start": "1", "notify_end": "1"})
    update_ok = flask_ui_client.post("/ui/scheduler/job/nightly/update", data={"label": "Nightly Sync", "cron": "0 3 * * *", "enabled": "1", "steps": ["borg.run"], "notify_start": "1", "notify_end": "1"})
    trigger_ok = flask_ui_client.post("/ui/scheduler/job/nightly/trigger")

    assert invalid.status_code == 422
    assert "Pflichtfelder" in invalid.get_data(as_text=True)
    assert create_ok.status_code == 200
    assert update_ok.status_code == 200
    assert trigger_ok.status_code == 200