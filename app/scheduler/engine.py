# scheduler/engine.py
# Vereinfachtes Single-Job-Konzept: genau ein Backup-Job "backup"
# Konfiguration in SQLite (settings-Tabelle), kein YAML mehr
import threading
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler = BackgroundScheduler(timezone="Europe/Berlin")
_lock = threading.Lock()

JOB_ID = "backup"


# ── DB-Zugriff ────────────────────────────────────────────────────

def _get_setting(key: str, default: str = "") -> str:
    from api.storage import get_setting
    return get_setting(key, default)


def _set_setting(key: str, value: str) -> None:
    from api.storage import set_setting
    set_setting(key, value)


# ── Internes Registrieren ─────────────────────────────────────────

def _register() -> None:
    if _scheduler.get_job(JOB_ID):
        _scheduler.remove_job(JOB_ID)
    if _get_setting("scheduler_enabled", "0") != "1":
        return
    cron = _get_setting("scheduler_cron", "0 2 * * *").strip()
    if not cron:
        return
    from scheduler.runner import run_backup
    _scheduler.add_job(
        func=run_backup,
        trigger=CronTrigger.from_crontab(cron, timezone="Europe/Berlin"),
        id=JOB_ID,
        name="Backup",
        kwargs={"job_id": JOB_ID, "modules": [], "debug": False},
        replace_existing=True,
        misfire_grace_time=300,
    )


def init_scheduler() -> None:
    if _scheduler.running:
        return
    _register()
    _scheduler.start()


# ── Public API ────────────────────────────────────────────────────

def get_config() -> dict:
    apjob = _scheduler.get_job(JOB_ID) if _scheduler.running else None
    next_run = apjob.next_run_time.strftime("%d.%m.%Y %H:%M") if apjob and apjob.next_run_time else None
    return {
        "cron":       _get_setting("scheduler_cron", "0 2 * * *"),
        "enabled":    _get_setting("scheduler_enabled", "0") == "1",
        "next_run":   next_run,
        "last_run":   _get_setting("scheduler_last_run", ""),
        "last_status": _get_setting("scheduler_last_status", ""),
        "last_duration": _get_setting("scheduler_last_duration", ""),
    }


def update_config(cron: str | None = None, enabled: bool | None = None) -> dict:
    with _lock:
        if cron is not None:
            _set_setting("scheduler_cron", cron)
        if enabled is not None:
            _set_setting("scheduler_enabled", "1" if enabled else "0")
        _register()
    return get_config()


def trigger_now(debug: bool = False) -> None:
    from scheduler.runner import run_backup
    threading.Thread(
        target=run_backup,
        kwargs={"job_id": JOB_ID, "modules": [], "debug": debug},
        daemon=True,
    ).start()


def update_job_result(job_id: str, status: str, duration: str) -> None:
    with _lock:
        _set_setting("scheduler_last_run", datetime.now().strftime("%d.%m.%Y %H:%M"))
        _set_setting("scheduler_last_status", status)
        _set_setting("scheduler_last_duration", duration)


def get_running_jobs() -> list:
    from scheduler.runner import _running_jobs
    return list(_running_jobs)


# Legacy-Kompatibilität für alte Scheduler-Router-Aufrufe
def list_jobs() -> list:
    cfg = get_config()
    return [{"id": JOB_ID, "description": "Backup", **cfg, "modules": []}]


def get_job(job_id: str):
    if job_id != JOB_ID:
        return None
    return {"id": JOB_ID, "description": "Backup", **get_config(), "modules": []}
