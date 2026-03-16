"""Tests fuer Modul-Laden und Registry-Abdeckung."""

from core.ui.module_registry import load_modules


def test_load_modules_enthaelt_app_und_core_module():
    from tests.conftest import APP_ROOT

    modules = load_modules(APP_ROOT)
    keys = {module.key for module in modules}

    assert {
        "borg",
        "errors",
        "history",
        "notify",
        "proxmox_hosts",
        "proxmox_jobs",
        "proxmox_lxc",
        "remotes",
        "rsync",
        "scheduler",
        "settings",
        "sysinfo",
    }.issubset(keys)


def test_geladene_module_haben_nav_und_ui_oder_api():
    from tests.conftest import APP_ROOT

    modules = load_modules(APP_ROOT)

    for module in modules:
        assert module.nav_url
        assert module.ui_blueprint is not None or module.api_router is not None