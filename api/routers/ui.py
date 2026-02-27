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
