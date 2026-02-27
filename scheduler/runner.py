# scheduler/runner.py
import subprocess
import time
from datetime import datetime
from helpers.logger import log, set_log_context, clear_log_context
from helpers.notify import notify_ntfy
from config import set_debug

_running_jobs: set = set()

BACKUP02_HOST = "backup02.simpsons.lan"
BACKUP02_USER = "backupadm"


def _power_on_backup02():
    subprocess.run(["wakeonlan", "68:05:ca:3e:99:7b"], check=True)
    log("INFO", "→ backup02 gestartet (Wake-on-LAN gesendet)")


def _wait_for_backup02():
    log("INFO", "→ Warte bis backup02 erreichbar ist …")
    while True:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{BACKUP02_USER}@{BACKUP02_HOST}", "echo ok"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and "ok" in result.stdout:
            log("INFO", "✔ backup02 ist online")
            return
        time.sleep(10)


def _power_off_backup02():
    subprocess.run(["ssh", f"{BACKUP02_USER}@{BACKUP02_HOST}", "sudo shutdown -h now"], check=True)
    log("INFO", "→ backup02 heruntergefahren")


def _format_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h: parts.append(f"{h} Stunde{'n' if h > 1 else ''}")
    if m: parts.append(f"{m} Minute{'n' if m > 1 else ''}")
    if s or not parts: parts.append(f"{s} Sekunde{'n' if s != 1 else ''}")
    return " und ".join(parts)


def run_backup(job_id: str, modules: list, debug: bool = False) -> None:
    if job_id in _running_jobs:
        log("WARNING", f"Job '{job_id}' läuft bereits – übersprungen")
        return

    _running_jobs.add(job_id)
    set_log_context("scheduler", job_id)
    set_debug(debug)
    start = datetime.now()
    status = "OK"

    try:
        log("INFO", f"{'='*40}")
        log("INFO", f"Job '{job_id}' gestartet – Module: {modules or ['alle']}{' [DEBUG]' if debug else ''}")
        if not debug:
            notify_ntfy(f"Backup gestartet: {job_id}", priority="low")
            _power_on_backup02()
            _wait_for_backup02()

        run_all = not modules

        if run_all or "borg" in modules:
            from modules import borg
            borg.run()

        if run_all or "rsync" in modules:
            from modules import rsync
            rsync.run()

        if run_all or "proxmox" in modules:
            from modules import proxmox
            proxmox.run()

        if not debug:
            _power_off_backup02()

    except Exception as e:
        status = "FEHLER"
        log("WARNING", f"Job '{job_id}' fehlgeschlagen: {e}")
        if not debug:
            notify_ntfy(f"Backup FEHLER – Job '{job_id}': {e}", priority="high")

    finally:
        _running_jobs.discard(job_id)
        set_debug(False)
        duration_str = _format_duration(int((datetime.now() - start).total_seconds()))
        log("INFO", f"Job '{job_id}' beendet – Status: {status} – Dauer: {duration_str}")
        log("INFO", f"{'='*40}")
        clear_log_context()
        if not debug:
            notify_ntfy(f"Backup {status}: {job_id}\nDauer: {duration_str}",
                        priority="low" if status == "OK" else "high")
        from scheduler.engine import update_job_result
        update_job_result(job_id, status, duration_str)
