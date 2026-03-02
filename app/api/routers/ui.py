# api/routers/ui.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from api.templates import templates
from fastapi.responses import HTMLResponse

from ..storage import load_config

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

router = APIRouter(tags=["tabs"])

ALLOWED_MODULES = {"borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"}

@router.get("/{module}/tab", response_class=HTMLResponse)
def tab_module_wrapper(request: Request, module: str):
    if module == "repos":
        from api.routers.repos import repos_tab
        return repos_tab(request)

    if module == "browser":
        from api.routers.browser import browser_tab
        return browser_tab(request)

    if module == "stats":
        from api.routers.stats import stats_tab
        return stats_tab(request)

    if module == "sysinfo":
        from api.routers.sysinfo import sysinfo_tab
        return sysinfo_tab(request)

    if module == "history":
        from api.routers.history import history_tab
        return history_tab(request)
    if module == "settings":
        import json as _j
        from helpers.secrets import get_secret_safe
        from api.storage import get_setting
        # WoL und ntfy aus SQLite lesen (keine Secrets)
        try:
            wol_entries = _j.loads(get_setting("wol_entries", "[]"))
        except Exception:
            wol_entries = []
        if not wol_entries:
            wol_entries = [{"mac": "", "host": ""}]
        return templates.TemplateResponse("partials/settings/tab.html", {
            "request": request,
            "ntfy_server":         get_setting("ntfy_server", ""),
            "ntfy_topic":          get_setting("ntfy_topic",  ""),
            "wol_entries":         wol_entries,
            "borg_passphrase_set": bool(get_secret_safe("BORG_PASSPHRASE")),
            "pbs_password_set":    bool(get_secret_safe("PBS_PASSWORD")),
            "pbs_fingerprint_set": bool(get_secret_safe("PBS_FINGERPRINT")),
            "scheduler_cron":      _get_scheduler_cron(),
            "scheduler_enabled":   _get_scheduler_enabled(),
            "repos_base_path":     get_setting("repos_base_path", ""),
        })

    if module == "scheduler":
        import scheduler.engine as engine
        return templates.TemplateResponse("partials/scheduler/tab.html", {
            "request": request,
            "jobs": engine.list_jobs(),
            "running": engine.get_running_jobs(),
            "container_id": "tab-scheduler",
            "loading_id": "scheduler-loading",
        })

    if module == "errors":
        from helpers.logger import get_all_errors
        return templates.TemplateResponse("partials/errors/tab.html", {
            "request": request,
            "errors": get_all_errors(),
        })

    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Module not found")

    cfg = load_config(module)
    from api.routers.run import get_running

    context = {
        "request": request,
        "cfg": cfg,
        "module": module,
        "title": module.replace("_", " ").title(),
        "container_id": f"tab-{module}",
        "loading_id": f"{module}-loading",
        "list_wrapper": "partials/list_wrapper.html",
        "content_template": f"partials/lists/{module}.html",
        "endpoint": f"/api/ui/{module}",
        "running": get_running(),
    }

    return templates.TemplateResponse("partials/tab_wrapper.html", context)

@router.get("/{module}/list", response_class=HTMLResponse)
def tab_module_list(request: Request, module: str):
    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Module not found")
    cfg = load_config(module)
    from api.routers.run import get_running
    context = {
        "request": request,
        "cfg": cfg,
        "running": get_running(),
    }
    return templates.TemplateResponse(f"partials/lists/{module}.html", context)


def _get_scheduler_cron() -> str:
    import scheduler.engine as engine
    jobs = engine.list_jobs()
    return jobs[0]["cron"] if jobs else "0 2 * * *"


def _get_scheduler_enabled() -> bool:
    import scheduler.engine as engine
    jobs = engine.list_jobs()
    return jobs[0]["enabled"] if jobs else False


def _get_setting(key: str, default: str = "") -> str:
    from api.storage import get_setting
    return get_setting(key, default)
