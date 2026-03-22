# modules/proxmox_lxc.py
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.system.logger import log, log_context, set_log_context
from core.system.reachability import require_hosts
from core.system.cmd import run_cmd, build_connection_string
from api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item
from core.ui.settings_registry import get_module as _get_module_setting, get as _get_global_setting

def _get_config(): return _load_config("proxmox_lxc")


def _get_proxmox_host_info(entry: dict) -> tuple[str, str, int, str]:
    """
    Returns (ssh_host, ssh_user, ssh_port, node_name).
    node_name is derived from the remote host before the first dot.
    Falls back to legacy host/node fields.
    """
    remote_id = entry.get("node")
    if remote_id:
        from core.modules.remotes.engine import get_remote_ssh, get_remote
        try:
            ssh_host, ssh_user, ssh_port = get_remote_ssh(remote_id)
            node_name = ssh_host.split(".")[0]
            return (ssh_host, ssh_user, ssh_port, node_name)
        except ValueError as e:
            log("ERROR", str(e))
            raise
    elif entry.get("host"):
        host = entry["host"]
        return (host, entry.get("ssh_user", "backupadm"), 22, host.split(".")[0])
    else:
        raise ValueError("Job: kein Node / Remote Device konfiguriert")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), item_id)
    if entry is None:
        return []

    node = entry.get("node")
    vmid = entry.get("vmid")
    if not node or vmid is None:
        return []

    try:
        ssh_host, ssh_user, ssh_port, node_name = _get_proxmox_host_info(entry)
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    connection = build_connection_string(ssh_host, ssh_user)

    storage             = _get_module_setting("proxmox_lxc", "backup_storage", "backup01")
    mode                = _get_module_setting("proxmox_lxc", "backup_mode", "snapshot")
    notes_template      = _get_module_setting("proxmox_lxc", "notes_template", "{{guestname}}")
    ssh_connect_timeout = _get_module_setting("proxmox_lxc", "ssh_connect_timeout", 10)

    cmd_parts = [
        "sudo", "/usr/bin/vzdump", str(vmid),
        "--fleecing", "0", "--node", node_name,
        "--mode", mode,
        "--notification-mode", "notification-system",
        "--notes-template", notes_template,
        "--storage", storage, "--all", "0",
    ]
    cmd_str = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout={ssh_connect_timeout} {connection} '{cmd_str}'"

    return [{"label": "vzdump", "cmd": full_cmd}]


def run():
    config = _get_config()
    grouped = group_by_node(config)
    if not grouped:
        return

    # Resolve SSH info per remote_id and check reachability
    node_infos = {}
    for remote_id, jobs in grouped.items():
        try:
            ssh_host, ssh_user, ssh_port, node_name = _get_proxmox_host_info({"node": remote_id})
        except ValueError as e:
            log("ERROR", str(e))
            continue
        if not require_hosts([ssh_host], user=ssh_user):
            continue
        node_infos[remote_id] = (ssh_host, ssh_user, ssh_port, node_name, jobs)

    if not node_infos:
        return

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_run_node, node_name, ssh_host, ssh_user, jobs): node_name
            for _, (ssh_host, ssh_user, ssh_port, node_name, jobs) in node_infos.items()
        }
        for future in as_completed(futures):
            node_name = futures[future]
            try:
                future.result()
            except Exception as e:
                log("ERROR", f"Node '{node_name}': {e}")


def run_single(item_id, entry=None):
    entry = _get_entry(_get_config(), item_id)
    if not entry:
        log("ERROR", f"LXC-Eintrag '{item_id}' nicht gefunden")
        return
    with log_context("proxmox_lxc", item_id):
        node = entry.get("node")
        vmid = entry.get("vmid")
        if not node or vmid is None:
            log("ERROR", f"LXC-Eintrag '{item_id}': Pflichtfelder (node, vmid) fehlen")
            return

        try:
            ssh_host, ssh_user, ssh_port, node_name = _get_proxmox_host_info(entry)
        except ValueError as e:
            log("ERROR", str(e))
            return

        log("INFO", f"=== LXC '{entry.get('description', item_id)}' gestartet ===")
        if not require_hosts([ssh_host], user=ssh_user):
            return
        connection = build_connection_string(ssh_host, ssh_user)
        _backup_lxc(vmid, entry.get("description", item_id), node_name, connection)
        from datetime import datetime
        _patch_item("proxmox_lxc", item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))
        log("INFO", f"=== LXC '{entry.get('description', item_id)}' abgeschlossen ===")


def _run_node(node, ssh_host, ssh_user, jobs):
    from core.modules.scheduler.job_runner import run_logged
    from datetime import datetime
    connection = build_connection_string(ssh_host, ssh_user)
    for job in jobs:
        vmid     = job["vmid"]
        name     = job["name"]
        item_id  = job.get("item_id")
        try:
            run_logged("proxmox_lxc", str(item_id), name,
                       lambda v=vmid, n=name, c=connection: _backup_lxc(v, n, node, c))
        finally:
            if item_id is not None:
                _patch_item("proxmox_lxc", item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))


def _backup_lxc(vmid, name, node, connection):
    storage             = _get_module_setting("proxmox_lxc", "backup_storage", "backup01")
    mode                = _get_module_setting("proxmox_lxc", "backup_mode", "snapshot")
    notes_template      = _get_module_setting("proxmox_lxc", "notes_template", "{{guestname}}")
    ssh_connect_timeout = _get_global_setting("ssh_connect_timeout", 10)

    cmd = [
        "sudo", "/usr/bin/vzdump", str(vmid),
        "--fleecing", "0", "--node", node,
        "--mode", mode,
        "--notification-mode", "notification-system",
        "--notes-template", notes_template,
        "--storage", storage, "--all", "0"
    ]
    try:
        run_cmd(cmd, connection, ssh_connect_timeout=ssh_connect_timeout)
        log("INFO", f"LXC '{name}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"LXC '{name}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def group_by_node(config):
    grouped = defaultdict(list)
    for item_id, entry in config.items():
        if not entry.get("enabled", False):
            continue
        node = entry.get("node")
        vmid = entry.get("vmid")
        if not node or vmid is None:
            log("WARNING", f"LXC-Eintrag '{item_id}': Pflichtfelder (node, vmid) fehlen, übersprungen")
            continue
        grouped[node].append(
            {"vmid": vmid, "name": entry.get("description", item_id), "item_id": item_id})
    return grouped
