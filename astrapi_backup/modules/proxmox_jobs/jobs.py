# modules/proxmox_jobs.py
import subprocess

from astrapi.core.system.logger import log, log_context
from astrapi.core.system.reachability import require_hosts
from astrapi.core.system.cmd import run_cmd, build_connection_string
from astrapi_backup.api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item

def _get_config(): return _load_config("proxmox_jobs")


def _get_proxmox_host_info(entry: dict) -> tuple[str, str, int]:
    """Get proxmox host info from remote device or legacy host field"""
    if entry.get("remote_id"):
        from astrapi_backup.modules.remotes.engine import get_remote_ssh
        try:
            return get_remote_ssh(entry["remote_id"])
        except ValueError as e:
            log("ERROR", str(e))
            raise
    elif entry.get("host"):
        return (entry["host"], entry.get("ssh_user"), 22)
    else:
        raise ValueError("Job missing: neither 'remote_id' nor 'host' configured")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    job = _get_entry(_get_config(), item_id)
    if job is None:
        return []

    job_name = job.get("job")
    job_type = job.get("type")
    if not job_name or not job_type:
        return []

    try:
        host, ssh_user, ssh_port = _get_proxmox_host_info(job)
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    connection = build_connection_string(host, ssh_user)

    cmd_parts = ["sudo", "/usr/sbin/proxmox-backup-manager",
                 f"{job_type}-job", "run", job_name]
    cmd_str   = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    return [{"label": f"{job_type}-job", "cmd": full_cmd}]


def run():
    from astrapi.core.modules.scheduler.job_runner import run_all
    run_all("proxmox_jobs", _get_config(), run_single,
            desc_fn=lambda iid, e: e.get("description", e.get("job", iid)))


def run_by_type(job_type: str):
    """Führt alle aktivierten Jobs eines bestimmten Typs sequenziell aus."""
    from astrapi.core.modules.scheduler.job_runner import run_all
    filtered = {iid: e for iid, e in _get_config().items() if e.get("type") == job_type}
    run_all("proxmox_jobs", filtered, run_single,
            desc_fn=lambda iid, e: e.get("description", e.get("job", iid)))


def run_single(item_id, job=None):
    if job is None:
        job = _get_entry(_get_config(), item_id)
    if job is None:
        log("ERROR", f"Proxmox-Job '{item_id}' nicht gefunden")
        return
    with log_context("proxmox_jobs", item_id):
        job_name = job.get("job")
        job_type = job.get("type")
        if not job_name or not job_type:
            log("ERROR", f"Proxmox-Job '{item_id}': Pflichtfelder (job, type) fehlen")
            return

        try:
            host, ssh_user, ssh_port = _get_proxmox_host_info(job)
        except ValueError as e:
            log("ERROR", str(e))
            return

        desc = job.get("description", job_name)
        log("INFO", f"=== Job '{desc}' ({job_type}) gestartet ===")
        if not require_hosts([host], user=ssh_user):
            return
        _run(job_type, job_name, host, ssh_user)
        from datetime import datetime
        _patch_item("proxmox_jobs", item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))
        log("INFO", f"=== Job '{desc}' abgeschlossen ===")


def _run(job_type, job_name, host, ssh_user):
    connection = build_connection_string(host, ssh_user)
    cmd = ["sudo", "/usr/sbin/proxmox-backup-manager",
           f"{job_type}-job", "run", job_name]
    try:
        run_cmd(cmd, connection)
        log("INFO", f"{job_type}-job '{job_name}' auf '{host}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"{job_type}-job '{job_name}' auf '{host}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
