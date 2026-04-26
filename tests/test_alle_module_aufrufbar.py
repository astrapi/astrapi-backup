"""
tests/test_module_routes.py

Prüft ob jedes registrierte Modul über GET /ui/{key}/content erreichbar ist
(HTTP 200). Deckt alle App-Module und alle Core-Module ab.
"""

import pytest

# App-eigene Module (aus astrapi_backup/navigation.yaml)
APP_MODULES = [
    "borg",
    "rsync",
    "proxmox_lxc",
    "proxmox_hosts",
    "proxmox_jobs",
    "remotes",
]

# Core-Module (aus astrapi_core/navigation.yaml)
CORE_MODULES = [
    "activity_log",
    "notify",
    "scheduler",
    "system",
    "settings",
]

ALL_MODULES = APP_MODULES + CORE_MODULES


@pytest.mark.parametrize("key", ALL_MODULES, ids=ALL_MODULES)
def test_content_route_returns_200(client, key):
    """GET /ui/{key}/content muss HTTP 200 zurückliefern."""
    resp = client.get(f"/ui/{key}/content")
    assert resp.status_code == 200, (
        f"GET /ui/{key}/content → HTTP {resp.status_code}\n{resp.text[:500]}"
    )
