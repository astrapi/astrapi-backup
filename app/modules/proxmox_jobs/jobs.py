# modules/proxmox_jobs.py
import subprocess

from core.system.logger import log, log_context
from core.system.reachability import require_hosts
from core.system.cmd import run_cmd, build_connection_string
from api.storage import load_config as _load_config, get_entry as _get_entry
def _get_config(): return _load_config("proxmox_jobs")


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    job = _get_entry(_get_config(), item_id)
    if job is None:
        return []

    job_name = job.get("job")
    job_type = job.get("type")
    host     = job.get("host")
    if not job_name or not job_type or not host:
        return []
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
    from core.modules.scheduler.job_runner import run_all
    run_all("proxmox_jobs", _get_config(), run_single,
            desc_fn=lambda iid, e: e.get("description", e.get("job", iid)))


def run_by_type(job_type: str):
    """Führt alle aktivierten Jobs eines bestimmten Typs sequenziell aus."""
    from core.modules.scheduler.job_runner import run_all
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
        host     = job.get("host")
        if not job_name or not job_type or not host:
            log("ERROR", f"Proxmox-Job '{item_id}': Pflichtfelder (job, type, host) fehlen")
            return
        desc = job.get("description", job_name)
        log("INFO", f"=== Job '{desc}' ({job_type}) gestartet ===")
        if not require_hosts([host]):
            return
        _run(job_type, job_name, host)
        log("INFO", f"=== Job '{desc}' abgeschlossen ===")



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
