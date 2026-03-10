# api/routers/history.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from api.templates import templates
from api.storage import list_history

router = APIRouter(tags=["history"])


def _fmt_duration(s: int | None) -> str:
    if s is None:
        return "—"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, min_ = divmod(m, 60)
    return f"{h}h {min_}m"


@router.get("/tab", response_class=HTMLResponse)
def history_tab(request: Request, module: str = ""):
    entries = list_history(limit=200, module=module or None)
    for e in entries:
        e["duration_fmt"] = _fmt_duration(e.get("duration_s"))
    return templates.TemplateResponse("history/partials/tab.html", {
        "request": request,
        "entries": entries,
        "filter_module": module,
        "modules": ["borg", "rsync", "proxmox_lxc", "proxmox_hosts", "proxmox_jobs"],
    })


@router.get("/rows", response_class=HTMLResponse)
def history_rows(request: Request, module: str = ""):
    entries = list_history(limit=200, module=module or None)
    for e in entries:
        e["duration_fmt"] = _fmt_duration(e.get("duration_s"))
    return templates.TemplateResponse("history/partials/rows.html", {
        "request": request,
        "entries": entries,
    })
