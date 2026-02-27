# scheduler/engine.py
import threading
import yaml
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

CONFIG_PATH = Path("config/scheduler.yaml")
_scheduler = BackgroundScheduler(timezone="Europe/Berlin")
_lock = threading.Lock()


def _load() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text("{}\n", encoding="utf-8")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _save(data: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _register(job_id: str, entry: dict) -> None:
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    if not entry.get("enabled", False):
        return
    cron = entry.get("cron", "").strip()
    if not cron:
        return
    from scheduler.runner import run_backup
    _scheduler.add_job(
        func=run_backup,
        trigger=CronTrigger.from_crontab(cron, timezone="Europe/Berlin"),
        id=job_id,
        name=entry.get("description", job_id),
        kwargs={"job_id": job_id, "modules": entry.get("modules", []), "debug": False},
        replace_existing=True,
        misfire_grace_time=300,
    )


def init_scheduler() -> None:
    data = _load()
    for job_id, entry in data.items():
        _register(job_id, entry)
    _scheduler.start()


def list_jobs() -> list:
    data = _load()
    jobs = []
    for job_id, entry in data.items():
        apjob = _scheduler.get_job(job_id)
        next_run = None
        if apjob and apjob.next_run_time:
            next_run = apjob.next_run_time.strftime("%d.%m.%Y %H:%M")
        jobs.append({
            "id": job_id,
            "description": entry.get("description", job_id),
            "cron": entry.get("cron", ""),
            "modules": entry.get("modules", []),
            "enabled": entry.get("enabled", False),
            "next_run": next_run,
            "last_run": entry.get("last_run"),
            "last_status": entry.get("last_status"),
            "last_duration": entry.get("last_duration"),
        })
    return jobs


def get_job(job_id: str):
    data = _load()
    entry = data.get(job_id)
    return {"id": job_id, **entry} if entry else None


def create_job(job_id, description, cron, modules, enabled=True):
    with _lock:
        data = _load()
        if job_id in data:
            raise ValueError(f"Job '{job_id}' existiert bereits")
        entry = {"description": description, "cron": cron, "modules": modules, "enabled": enabled}
        data[job_id] = entry
        _save(data)
        _register(job_id, entry)
        return {"id": job_id, **entry}


def update_job(job_id, **kwargs):
    with _lock:
        data = _load()
        if job_id not in data:
            raise KeyError(f"Job '{job_id}' nicht gefunden")
        entry = data[job_id]
        for k in ("description", "cron", "modules", "enabled"):
            if k in kwargs:
                entry[k] = kwargs[k]
        data[job_id] = entry
        _save(data)
        _register(job_id, entry)
        return {"id": job_id, **entry}


def delete_job(job_id) -> bool:
    with _lock:
        data = _load()
        if job_id not in data:
            return False
        del data[job_id]
        _save(data)
        if _scheduler.get_job(job_id):
            _scheduler.remove_job(job_id)
        return True


def toggle_job(job_id):
    with _lock:
        data = _load()
        if job_id not in data:
            raise KeyError(f"Job '{job_id}' nicht gefunden")
        data[job_id]["enabled"] = not data[job_id].get("enabled", False)
        _save(data)
        _register(job_id, data[job_id])
        return {"id": job_id, **data[job_id]}


def trigger_job(job_id, debug=False):
    data = _load()
    if job_id not in data:
        raise KeyError(f"Job '{job_id}' nicht gefunden")
    from scheduler.runner import run_backup
    threading.Thread(
        target=run_backup,
        kwargs={"job_id": job_id, "modules": data[job_id].get("modules", []), "debug": debug},
        daemon=True,
    ).start()


def update_job_result(job_id, status, duration):
    with _lock:
        data = _load()
        if job_id not in data:
            return
        data[job_id]["last_run"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        data[job_id]["last_status"] = status
        data[job_id]["last_duration"] = duration
        _save(data)


def get_running_jobs() -> list:
    from scheduler.runner import _running_jobs
    return list(_running_jobs)
