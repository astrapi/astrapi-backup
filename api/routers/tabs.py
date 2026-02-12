# api/routers/tabs.py
from pathlib import Path
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..storage import load_config

ROOT = Path(__file__).resolve().parents[1]  # api/..
PROJECT_ROOT = ROOT.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
CONFIG_DIR = PROJECT_ROOT / "config"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["tabs"])

@router.get("/api/tabs/borg", response_class=HTMLResponse)
def tab_borg(request: Request):
    cfg = load_config("borg")
    return templates.TemplateResponse("partials/borg/tab.html", {"request": request, "cfg": cfg})

@router.get("/api/tabs/proxmox/jobs", response_class=HTMLResponse)
def tab_proxmox_jobs(request: Request):
    cfg = load_config("proxmox_jobs")
    return templates.TemplateResponse("partials/proxmox_jobs/tab.html", {"request": request, "cfg": cfg})

@router.get("/api/tabs/proxmox/lxc", response_class=HTMLResponse)
def tab_proxmox_lxc(request: Request):
    cfg = load_config("proxmox_lxc")
    return templates.TemplateResponse("partials/proxmox_lxc/tab.html", {"request": request, "cfg": cfg})

@router.get("/api/tabs/proxmox/hosts", response_class=HTMLResponse)
def tab_proxmox_hosts(request: Request):
    cfg = load_config("proxmox_hosts")
    return templates.TemplateResponse("partials/proxmox_hosts/tab.html", {"request": request, "cfg": cfg})

@router.get("/api/tabs/rsync", response_class=HTMLResponse)
def tab_rsync(request: Request):
    cfg = load_config("rsync2")
    return templates.TemplateResponse("partials/rsync/tab.html", {"request": request, "cfg": cfg})
