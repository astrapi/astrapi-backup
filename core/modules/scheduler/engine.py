# core/modules/scheduler/engine.py
"""Scheduler-Singleton für das Core-Scheduler-Modul.

Projekte registrieren ihre Job-Funktion via configure() bevor init() aufgerufen wird:

    from core.modules.scheduler.engine import configure, init

    configure(
        job_fn=my_job,
        get_setting=storage.get,
        set_setting=storage.set,
        job_name="Nightly Sync",
    )
    init()
"""
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class Scheduler:
    def __init__(
        self,
        job_fn,
        get_setting,
        set_setting,
        job_id: str = "main",
        job_name: str = "Job",
        job_kwargs: dict = None,
        timezone: str = "Europe/Berlin",
        cron_key: str = "scheduler_cron",
        enabled_key: str = "scheduler_enabled",
        default_cron: str = "0 2 * * *",
    ):
        self._job_fn       = job_fn
        self._get          = get_setting
        self._set          = set_setting
        self._job_id       = job_id
        self._job_name     = job_name
        self._job_kwargs   = job_kwargs or {}
        self._timezone     = timezone
        self._cron_key     = cron_key
        self._enabled_key  = enabled_key
        self._default_cron = default_cron
        self._lock         = threading.Lock()
        self._scheduler    = BackgroundScheduler(timezone=timezone)

    def _register(self) -> None:
        if self._scheduler.get_job(self._job_id):
            self._scheduler.remove_job(self._job_id)
        if self._get(self._enabled_key, "0") != "1":
            return
        cron = self._get(self._cron_key, self._default_cron).strip()
        if not cron:
            return
        self._scheduler.add_job(
            func=self._job_fn,
            trigger=CronTrigger.from_crontab(cron, timezone=self._timezone),
            id=self._job_id,
            name=self._job_name,
            kwargs=self._job_kwargs,
            replace_existing=True,
            misfire_grace_time=300,
        )

    def init(self) -> None:
        if self._scheduler.running:
            return
        self._register()
        self._scheduler.start()

    def get_config(self) -> dict:
        apjob = self._scheduler.get_job(self._job_id) if self._scheduler.running else None
        next_run = (
            apjob.next_run_time.strftime("%d.%m.%Y %H:%M")
            if apjob and apjob.next_run_time else None
        )
        return {
            "cron":          self._get(self._cron_key, self._default_cron),
            "enabled":       self._get(self._enabled_key, "0") == "1",
            "next_run":      next_run,
            "last_run":      self._get("scheduler_last_run", ""),
            "last_status":   self._get("scheduler_last_status", ""),
            "last_duration": self._get("scheduler_last_duration", ""),
        }

    def update_config(self, cron: str | None = None, enabled: bool | None = None) -> dict:
        with self._lock:
            if cron is not None:
                self._set(self._cron_key, cron)
            if enabled is not None:
                self._set(self._enabled_key, "1" if enabled else "0")
            self._register()
        return self.get_config()

    def trigger_now(self, **kwargs) -> None:
        merged = {**self._job_kwargs, **kwargs}
        threading.Thread(target=self._job_fn, kwargs=merged, daemon=True).start()

    def update_result(self, status: str, duration: str) -> None:
        with self._lock:
            self._set("scheduler_last_run", datetime.now().strftime("%d.%m.%Y %H:%M"))
            self._set("scheduler_last_status", status)
            self._set("scheduler_last_duration", duration)


# ── Singleton ─────────────────────────────────────────────────────────────────

_scheduler: Scheduler | None = None


def configure(
    job_fn,
    get_setting,
    set_setting,
    job_id: str = "main",
    job_name: str = "Job",
    job_kwargs: dict = None,
    timezone: str = "Europe/Berlin",
    cron_key: str = "scheduler_cron",
    enabled_key: str = "scheduler_enabled",
    default_cron: str = "0 2 * * *",
) -> None:
    global _scheduler
    _scheduler = Scheduler(
        job_fn=job_fn,
        get_setting=get_setting,
        set_setting=set_setting,
        job_id=job_id,
        job_name=job_name,
        job_kwargs=job_kwargs or {},
        timezone=timezone,
        cron_key=cron_key,
        enabled_key=enabled_key,
        default_cron=default_cron,
    )


def init() -> None:
    if _scheduler:
        _scheduler.init()


def get_config() -> dict:
    return _scheduler.get_config() if _scheduler else {
        "cron": "", "enabled": False, "next_run": None,
        "last_run": "", "last_status": "", "last_duration": "",
    }


def update_config(cron: str | None = None, enabled: bool | None = None) -> dict:
    return _scheduler.update_config(cron=cron, enabled=enabled) if _scheduler else get_config()


def trigger_now(**kwargs) -> None:
    if _scheduler:
        _scheduler.trigger_now(**kwargs)


def update_result(status: str, duration: str) -> None:
    if _scheduler:
        _scheduler.update_result(status, duration)


def is_configured() -> bool:
    return _scheduler is not None
