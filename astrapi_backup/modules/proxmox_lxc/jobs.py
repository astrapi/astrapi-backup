# modules/proxmox_lxc.py
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

from astrapi.core.system.logger import log, log_context
from astrapi.core.ui.settings_registry import get_module as _get_module_setting
from astrapi_backup.api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item

KEY = "proxmox_lxc"

def _get_config(): return _load_config(KEY)


def _verify_ssl() -> bool:
    return str(_get_module_setting(KEY, "pve_verify_ssl", False)).lower() in ("1", "true", "on", "yes")


def _resolve_node_for_vmid(vmid: int) -> tuple[str, str]:
    """Ermittelt via Cluster-API welcher Node den Container hat.
    Gibt (host, node_name) zurück.
    """
    from astrapi.core.system.secrets import get_secret_safe
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select

    token_id     = _get_module_setting(KEY, "pve_api_token_id", "").strip()
    token_secret = get_secret_safe(f"module.{KEY}.pve_api_token_secret", "").strip()
    if not token_id or not token_secret:
        raise ValueError("Read-Token nicht konfiguriert (pve_api_token_id / pve_api_token_secret)")

    verify_ssl = _verify_ssl()
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    remotes = get_all_remotes_for_select(type_filter="proxmox_node")
    hosts   = {r["host"].split(".")[0]: r["host"] for r in remotes if r.get("host")}

    if not hosts:
        raise ValueError("Keine Proxmox-Node-Remotes konfiguriert")

    first_host = next(iter(hosts.values()))
    headers    = _auth_headers(token_id, token_secret)
    url        = f"https://{first_host}:8006/api2/json/cluster/resources?type=vm"

    resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
    resp.raise_for_status()

    for r in resp.json().get("data", []):
        if int(r.get("vmid", 0)) == vmid:
            node_name = r["node"]
            host      = hosts.get(node_name, first_host)
            return host, node_name

    raise ValueError(f"VMID {vmid} nicht im Cluster gefunden")


def _backup_token() -> tuple[str, str]:
    from astrapi.core.system.secrets import get_secret_safe
    token_id     = _get_module_setting(KEY, "pve_backup_token_id", "").strip()
    token_secret = get_secret_safe(f"module.{KEY}.pve_backup_token_secret", "").strip()
    if not token_id or not token_secret:
        raise ValueError("Backup-Token nicht konfiguriert (pve_backup_token_id / pve_backup_token_secret)")
    return token_id, token_secret


def _auth_headers(token_id: str, token_secret: str) -> dict:
    return {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}


def _trigger_vzdump(host: str, node_name: str, vmid: int) -> str:
    """Startet vzdump via Proxmox API. Gibt den UPID des Tasks zurück."""
    token_id, token_secret = _backup_token()
    verify_ssl     = _verify_ssl()
    storage        = _get_module_setting(KEY, "backup_storage", "backup01")
    mode           = _get_module_setting(KEY, "backup_mode", "snapshot")
    notes_template = _get_module_setting(KEY, "notes_template", "{{guestname}}")

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url  = f"https://{host}:8006/api2/json/nodes/{node_name}/vzdump"
    data = {
        "vmid":           str(vmid),
        "storage":        storage,
        "mode":           mode,
        "notes-template": notes_template,
    }
    resp = requests.post(url, headers=_auth_headers(token_id, token_secret),
                         data=data, verify=verify_ssl, timeout=30)
    resp.raise_for_status()
    upid = resp.json().get("data", "")
    if not upid:
        raise ValueError("vzdump API: kein UPID in der Antwort")
    return upid


def _wait_for_task(host: str, node_name: str, upid: str,
                   poll_interval: int = 5, timeout: int = 3600) -> str:
    """Pollt den Task-Status bis er abgeschlossen ist. Gibt exitstatus zurück."""
    token_id, token_secret = _backup_token()
    verify_ssl = _verify_ssl()
    headers    = _auth_headers(token_id, token_secret)

    upid_enc = urllib.parse.quote(upid, safe="")
    url      = f"https://{host}:8006/api2/json/nodes/{node_name}/tasks/{upid_enc}/status"

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=15)
        resp.raise_for_status()
        data   = resp.json().get("data", {})
        status = data.get("status", "")
        if status == "stopped":
            return data.get("exitstatus", "unknown")
        time.sleep(poll_interval)
    raise TimeoutError(f"Task {upid} nicht innerhalb von {timeout}s abgeschlossen")


def preview(item_id) -> list[dict]:
    """Gibt den API-Aufruf zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), item_id)
    if entry is None:
        return []

    vmid = entry.get("vmid")
    if vmid is None:
        return []

    try:
        host, node_name = _resolve_node_for_vmid(int(vmid))
    except Exception as e:
        return [{"label": "Error", "cmd": str(e)}]

    storage  = _get_module_setting(KEY, "backup_storage", "backup01")
    mode     = _get_module_setting(KEY, "backup_mode", "snapshot")
    token_id = _get_module_setting(KEY, "pve_backup_token_id", "<backup-token-id>").strip() or "<backup-token-id>"

    url = f"https://{host}:8006/api2/json/nodes/{node_name}/vzdump"
    cmd = (
        f"curl -k -X POST "
        f"-H 'Authorization: PVEAPIToken={token_id}=<secret>' "
        f"'{url}' "
        f"-d 'vmid={vmid}' -d 'storage={storage}' -d 'mode={mode}'"
    )
    return [{"label": "vzdump (API)", "cmd": cmd}]


def run():
    config = _get_config()
    jobs = [
        {"item_id": item_id, "vmid": int(e["vmid"]), "name": e.get("description", item_id)}
        for item_id, e in config.items()
        if e.get("enabled") and e.get("vmid") is not None
    ]
    if not jobs:
        return

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_run_single_job, j["item_id"], j["vmid"], j["name"]): j["name"]
            for j in jobs
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                log("ERROR", f"LXC '{name}': {e}")


def run_single(item_id, entry=None):
    entry = _get_entry(_get_config(), item_id)
    if not entry:
        log("ERROR", f"LXC-Eintrag '{item_id}' nicht gefunden")
        return
    with log_context(KEY, item_id):
        vmid = entry.get("vmid")
        if vmid is None:
            log("ERROR", f"LXC-Eintrag '{item_id}': Pflichtfeld vmid fehlt")
            return
        name = entry.get("description", item_id)
        log("INFO", f"=== LXC '{name}' gestartet ===")
        _backup_lxc(int(vmid), name)
        from datetime import datetime
        _patch_item(KEY, item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))
        log("INFO", f"=== LXC '{name}' abgeschlossen ===")


def _run_single_job(item_id, vmid: int, name: str):
    from astrapi.core.modules.scheduler.job_runner import run_logged
    from datetime import datetime
    try:
        run_logged(KEY, str(item_id), name,
                   lambda v=vmid, n=name: _backup_lxc(v, n))
    finally:
        _patch_item(KEY, item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))


def _backup_lxc(vmid: int, name: str):
    try:
        host, node_name = _resolve_node_for_vmid(vmid)
        log("INFO", f"LXC '{name}': Node {node_name} ({host})")
        upid = _trigger_vzdump(host, node_name, vmid)
        log("INFO", f"LXC '{name}': Task gestartet ({upid})")
        exitstatus = _wait_for_task(host, node_name, upid)
        if exitstatus == "OK":
            log("INFO", f"LXC '{name}' erfolgreich")
        else:
            log("WARNING", f"LXC '{name}' abgeschlossen mit Status: {exitstatus}")
    except Exception as e:
        log("WARNING", f"LXC '{name}' fehlgeschlagen")
        log("ERROR", str(e))
