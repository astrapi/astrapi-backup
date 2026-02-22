# api/routers/ui.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..storage import load_config

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["tabs"])

ALLOWED_MODULES = {"borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"}

@router.get("/{module}/tab", response_class=HTMLResponse)
def tab_module_wrapper(request: Request, module: str):
    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Module not found")

    cfg = load_config(module)

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
    }

    return templates.TemplateResponse("partials/tab_wrapper.html", context)

@router.get("/{module}/list", response_class=HTMLResponse)
def tab_module_list(request: Request, module: str):
    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Module not found")
    cfg = load_config(module)
    context = {
        "request": request,
        "cfg": cfg,
    }
    return templates.TemplateResponse(f"partials/lists/{module}.html", context)
