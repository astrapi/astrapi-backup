# modules/proxmox_lxc.py
import subprocess
from collections import defaultdict

from core.system.logger import log, log_context, set_log_context
from core.system.reachability import require_hosts
from core.system.cmd import run_cmd, build_connection_string
from api.storage import load_config as _load_config, get_entry as _get_entry
from core.ui.settings_registry import get_module as _get_module_setting, get as _get_global_setting

def _get_config(): return _load_config("proxmox_lxc")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), item_id)
    if entry is None:
        return []

    node = entry.get("node")
    vmid = entry.get("vmid")
    if not node or vmid is None:
        return []
    connection = build_connection_string(node)

    storage             = _get_module_setting("proxmox_lxc", "backup_storage", "backup01")
    mode                = _get_module_setting("proxmox_lxc", "backup_mode", "snapshot")
    fleecing            = "1" if _get_module_setting("proxmox_lxc", "fleecing", False) else "0"
    notes_template      = _get_module_setting("proxmox_lxc", "notes_template", "{{guestname}}")
    ssh_connect_timeout = _get_module_setting("proxmox_lxc", "ssh_connect_timeout", 10)

    cmd_parts = [
        "sudo", "/usr/bin/vzdump", str(vmid),
        "--fleecing", fleecing, "--node", node,
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
    from core.modules.scheduler.job_runner import run_all
    run_all("proxmox_lxc", _get_config(), run_single)


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
        log("INFO", f"=== LXC '{entry.get('description', item_id)}' gestartet ===")
        if not require_hosts([node]):
            return
        _run_node(node,
                  [{"vmid": vmid, "name": entry.get("description", item_id), "item_id": item_id}])
        log("INFO", f"=== LXC '{entry.get('description', item_id)}' abgeschlossen ===")



def _run_node(node, jobs):
    connection = build_connection_string(node)
    for job in jobs:
        vmid = job["vmid"]
        name = job["name"]
        item_id = job.get("item_id")
        if item_id is not None:
            set_log_context("proxmox_lxc", item_id)
        storage              = _get_module_setting("proxmox_lxc", "backup_storage", "backup01")
        mode                 = _get_module_setting("proxmox_lxc", "backup_mode", "snapshot")
        fleecing             = "1" if _get_module_setting("proxmox_lxc", "fleecing", False) else "0"
        notes_template       = _get_module_setting("proxmox_lxc", "notes_template", "{{guestname}}")
        ssh_connect_timeout  = _get_global_setting("ssh_connect_timeout", 10)

        cmd = [
            "sudo", "/usr/bin/vzdump", str(vmid),
            "--fleecing", fleecing, "--node", node,
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
