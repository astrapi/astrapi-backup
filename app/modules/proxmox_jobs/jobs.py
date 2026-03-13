# modules/proxmox_jobs.py
import subprocess

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.cmd import run_cmd, build_connection_string
from api.storage import load_config as _load_config
def _get_config(): return _load_config("proxmox_jobs")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    job = _get_config().get(item_id) or _get_config().get(
        int(item_id) if str(item_id).isdigit() else item_id)
    if job is None:
        return []

    job_name   = job["job"]
    job_type   = job["type"]
    host       = job["host"]
    connection = build_connection_string(host)

    cmd_parts = ["sudo", "/usr/sbin/proxmox-backup-manager",
                 f"{job_type}-job", "run", job_name]
    cmd_str   = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    return [{"label": f"{job_type}-job", "cmd": full_cmd}]


def run():
    for item_id, job in _get_config().items():
        if not job.get("enabled", True):
            continue
        run_single(item_id, job)


def run_single(item_id, job=None):
    if job is None:
        job = _get_config().get(item_id) or _get_config().get(
            int(item_id) if str(item_id).isdigit() else item_id)
    if job is None:
        log("ERROR", f"Proxmox-Job '{item_id}' nicht gefunden")
        return
    set_log_context("proxmox_jobs", item_id)
    try:
        job_name = job["job"]
        job_type = job["type"]
        host     = job["host"]
        desc     = job.get("description", job_name)
        log("INFO", f"=== Job '{desc}' ({job_type}) gestartet ===")
        if not require_hosts([host]):
            return
        _run(job_type, job_name, host)
        log("INFO", f"=== Job '{desc}' abgeschlossen ===")
    finally:
        clear_log_context()


def _run(job_type, job_name, host):
    connection = build_connection_string(host)
    cmd = ["sudo", "/usr/sbin/proxmox-backup-manager",
           f"{job_type}-job", "run", job_name]
    try:
        run_cmd(cmd, connection)
        log("INFO", f"{job_type}-job '{job_name}' auf '{host}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"{job_type}-job '{job_name}' auf '{host}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
