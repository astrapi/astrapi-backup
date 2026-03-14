# modules/proxmox_hosts.py
import os
import subprocess

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.cmd import run_cmd, build_connection_string, is_local
from core.ui.settings_registry import get_module as _get_module_setting

from api.storage import load_config as _load_config
def _get_config(): return _load_config("proxmox_hosts")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_config().get(item_id) or _get_config().get(
        int(item_id) if str(item_id).isdigit() else item_id)
    if not entry:
        return []

    host       = entry.get("host", item_id)
    connection = build_connection_string(host)

    pxar_sources = [
        "etc.pxar:/etc", "home.pxar:/home", "opt.pxar:/opt",
        "root.pxar:/root", "local.pxar:/usr/local",
    ]
    pxar_sources += entry.get("source", [])

    pbs_repo = _get_module_setting("proxmox_hosts", "pbs_repository", "")

    cmd_parts = [
        f"PBS_REPOSITORY={pbs_repo}", "PBS_PASSWORD=***", "PBS_FINGERPRINT=***",
        "sudo", "--preserve-env=PBS_REPOSITORY,PBS_PASSWORD,PBS_FINGERPRINT",
        "/usr/bin/proxmox-backup-client", "backup", *pxar_sources,
        "--backup-type", "host", "--backup-id", "$(hostname)",
        "--ns", "host", "--backup-time", "$(date +%s)",
    ]
    cmd_str = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    return [{"label": "proxmox-backup-client", "cmd": full_cmd}]


def run():
    for item_id, entry in _get_config().items():
        if not entry.get("enabled", True):
            continue
        run_single(item_id, entry)


def run_single(item_id, entry=None):
    if entry is None:
        entry = _get_config().get(item_id) or _get_config().get(
            int(item_id) if str(item_id).isdigit() else item_id) or {}
    set_log_context("proxmox_hosts", item_id)
    try:
        host = entry.get("host", item_id)
        log("INFO", f"=== Host '{entry.get('description', host)}' gestartet ===")
        if not require_hosts([host]):
            return
        _backup(host, entry)
        log("INFO", f"=== Host '{entry.get('description', host)}' abgeschlossen ===")
    finally:
        clear_log_context()


def _backup(host, entry):
    connection = build_connection_string(host)

    pxar_sources = [
        "etc.pxar:/etc", "home.pxar:/home", "opt.pxar:/opt",
        "root.pxar:/root", "local.pxar:/usr/local",
    ]
    pxar_sources += entry.get("source", [])

    env = dict(os.environ)
    env["PBS_REPOSITORY"] = _get_module_setting("proxmox_hosts", "pbs_repository", "")
    env["PBS_PASSWORD"]    = _get_module_setting("proxmox_hosts", "pbs_password", "")
    env["PBS_FINGERPRINT"] = _get_module_setting("proxmox_hosts", "pbs_fingerprint", "")

    base_cmd = [
        "sudo", "--preserve-env=PBS_REPOSITORY,PBS_PASSWORD,PBS_FINGERPRINT",
        "/usr/bin/proxmox-backup-client", "backup", *pxar_sources,
        "--backup-type", "host", "--backup-id", "$(hostname)",
        "--ns", "host", "--backup-time", "$(date +%s)"
    ]

    if is_local(host):
        cmd = base_cmd
    else:
        cmd = [
            f"PBS_REPOSITORY={env['PBS_REPOSITORY']}",
            f"PBS_PASSWORD={env['PBS_PASSWORD']}",
            f"PBS_FINGERPRINT={env['PBS_FINGERPRINT']}",
            *base_cmd
        ]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", f"Host-Backup '{host}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Host-Backup '{host}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
