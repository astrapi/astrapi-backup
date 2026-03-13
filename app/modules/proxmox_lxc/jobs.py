# modules/proxmox_lxc.py
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.cmd import run_cmd, build_connection_string
from api.storage import load_config as _load_config
def _get_config(): return _load_config("proxmox_lxc")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_config().get(item_id) or _get_config().get(
        int(item_id) if str(item_id).isdigit() else item_id)
    if entry is None:
        return []

    node       = entry["node"]
    vmid       = entry["vmid"]
    connection = build_connection_string(node)

    cmd_parts = [
        "sudo", "/usr/bin/vzdump", str(vmid),
        "--fleecing", "0", "--node", node,
        "--mode", "snapshot",
        "--notification-mode", "notification-system",
        "--notes-template", "{{guestname}}",
        "--storage", "backup01", "--all", "0",
    ]
    cmd_str = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    return [{"label": "vzdump", "cmd": full_cmd}]


def run():
    grouped = group_by_node(_get_config())
    with ThreadPoolExecutor(max_workers=max(len(grouped), 1)) as executor:
        futures = [executor.submit(_run_node, node, jobs)
                   for node, jobs in grouped.items()]
        for f in futures:
            f.result()


def run_single(item_id):
    entry = _get_config().get(item_id) or _get_config().get(
        int(item_id) if str(item_id).isdigit() else item_id)
    if not entry:
        log("ERROR", f"LXC-Eintrag '{item_id}' nicht gefunden")
        return
    set_log_context("proxmox_lxc", item_id)
    try:
        log("INFO", f"=== LXC '{entry.get('description', item_id)}' gestartet ===")
        if not require_hosts([entry["node"]]):
            return
        _run_node(entry["node"],
                  [{"vmid": entry["vmid"], "name": entry.get("description", item_id)}])
        log("INFO", f"=== LXC '{entry.get('description', item_id)}' abgeschlossen ===")
    finally:
        clear_log_context()


def _run_node(node, jobs):
    connection = build_connection_string(node)
    for job in jobs:
        vmid = job["vmid"]
        name = job["name"]
        cmd = [
            "sudo", "/usr/bin/vzdump", str(vmid),
            "--fleecing", "0", "--node", node,
            "--mode", "snapshot",
            "--notification-mode", "notification-system",
            "--notes-template", "{{guestname}}",
            "--storage", "backup01", "--all", "0"
        ]
        try:
            run_cmd(cmd, connection)
            log("INFO", f"LXC '{name}' erfolgreich")
        except subprocess.CalledProcessError as e:
            log("WARNING", f"LXC '{name}' fehlgeschlagen")
            log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def group_by_node(config):
    grouped = defaultdict(list)
    for item_id, entry in config.items():
        if not entry.get("enabled", True):
            continue
        grouped[entry["node"]].append(
            {"vmid": entry["vmid"], "name": entry.get("description", item_id)})
    return grouped
