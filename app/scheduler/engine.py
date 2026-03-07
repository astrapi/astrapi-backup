# scheduler/engine.py
"""Konfiguriert den Core-Scheduler für backupctl."""
from core.modules.scheduler.engine import (
    configure, init, get_config, update_config,
    trigger_now, update_result, is_configured,
)
from api.storage import get_setting, set_setting
from scheduler.runner import run_backup

configure(
    job_fn=run_backup,
    get_setting=get_setting,
    set_setting=set_setting,
    job_id="backup",
    job_name="Backup",
    job_kwargs={"job_id": "backup", "modules": [], "debug": False},
    timezone="Europe/Berlin",
)


def init_scheduler() -> None:
    init()


# Legacy-Kompatibilität für Scheduler-Router und Settings-Tab
def get_running_jobs() -> list:
    from scheduler.runner import _running_jobs
    return list(_running_jobs)


def list_jobs() -> list:
    return [{"id": "backup", "description": "Backup", **get_config(), "modules": []}]


def get_job(job_id: str):
    if job_id != "backup":
        return None
    return {"id": "backup", "description": "Backup", **get_config(), "modules": []}


def update_job_result(job_id: str, status: str, duration: str) -> None:
    update_result(status, duration)
