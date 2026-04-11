# modules/proxmox_lxc/api.py
from pathlib import Path

from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_lxc.jobs import preview as _preview

KEY = "proxmox_lxc"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"

router = make_htmx_crud_router(KEY, _SCHEMA_PATH, preview_fn=_preview, running_fn=get_running)


def fetch_available_lxc() -> list[dict]:
    """Returns LXC containers from all proxmox_node remotes not yet registered.

    Uses /cluster/resources?type=vm (cluster-wide) and filters by type==lxc.
    Node names from the response are matched back to configured remotes.
    """
    import requests
    import urllib3
    from astrapi.core.system.db import load_config
    from astrapi.core.ui.settings_registry import get_module as _get_module_setting
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select

    registered = {
        int(e["vmid"])
        for e in load_config(KEY).values()
        if e.get("vmid") is not None
    }

    from astrapi.core.system.secrets import get_secret_safe
    token_id     = _get_module_setting(KEY, "pve_api_token_id", "").strip()
    token_secret = get_secret_safe(f"module.{KEY}.pve_api_token_secret", "").strip()
    verify_ssl   = str(_get_module_setting(KEY, "pve_verify_ssl", False)).lower() in ("1", "true", "on", "yes")

    if not token_id or not token_secret:
        return []

    # Build a map: node_name → remote_id and collect hosts
    node_remotes: dict[str, str] = {}
    hosts: dict[str, str] = {}  # remote_id → host
    for remote in get_all_remotes_for_select(type_filter="proxmox_node"):
        if remote["id"] == "local":
            continue
        host = remote.get("host", "")
        if not host:
            continue
        node_name = host.split(".")[0]
        node_remotes[node_name] = str(remote["id"])
        hosts[str(remote["id"])] = host

    if not hosts:
        return []

    # Use the first available remote to query cluster-wide resources
    first_remote_id = next(iter(hosts))
    host = hosts[first_remote_id]
    port = 8006

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    headers = {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}
    url = f"https://{host}:{port}/api2/json/cluster/resources?type=vm"
    try:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
        resp.raise_for_status()
        resources = resp.json().get("data", [])
    except Exception:
        return []

    result = []
    for ct in resources:
        if ct.get("type") != "lxc":
            continue
        vmid = int(ct.get("vmid", 0))
        if not vmid or vmid in registered:
            continue
        node_name = ct.get("node", "")
        remote_id = node_remotes.get(node_name, first_remote_id)
        result.append({
            "vmid":      vmid,
            "name":      ct.get("name", f"CT {vmid}"),
            "status":    ct.get("status", ""),
            "node_id":   remote_id,
            "node_host": host,
        })

    result.sort(key=lambda x: x["vmid"])
    return result
