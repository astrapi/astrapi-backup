# api/routers/run.py
import asyncio
import threading
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from config import set_debug
from helpers.logger import (get_log_dates, read_log, get_all_errors,
                             log_path, set_tee_context, clear_tee_context)
from api.storage import load_config

ROOT = Path(__file__).resolve().parents[2]
templates = None  # wird von api/templates.py gesetzt – Import unten

def _get_templates():
    global templates
    if templates is None:
        from api.templates import templates as t
        templates = t
    return templates

router = APIRouter(tags=["run"])

_running: dict = {}
_running_lock = threading.Lock()

MODULE_RUN_ID   = "__run__"    # item_id für normalen Modul-Gesamt-Run
MODULE_DEBUG_ID = "__debug__"  # item_id für Debug-Modul-Gesamt-Run


def _is_running(module: str, item_id: str) -> bool:
    return f"{module}:{item_id}" in _running

def _mark_running(module: str, item_id: str, mode: str) -> None:
    with _running_lock:
        _running[f"{module}:{item_id}"] = mode

def _mark_done(module: str, item_id: str) -> None:
    with _running_lock:
        _running.pop(f"{module}:{item_id}", None)

def get_running() -> dict:
    return dict(_running)


# ── Einzelnen Eintrag ausführen ───────────────────────────────────

@router.post("/{module}/{item_id}", response_class=HTMLResponse)
def run_item(module: str, item_id: str, request: Request, debug: bool = False):
    if _is_running(module, item_id):
        raise HTTPException(status_code=409, detail="Läuft bereits")

    def _execute():
        set_debug(debug)
        _mark_running(module, item_id, "debug" if debug else "run")
        try:
            _dispatch_single(module, item_id)
        finally:
            _mark_done(module, item_id)
            set_debug(False)

    threading.Thread(target=_execute, daemon=True).start()

    cfg = load_config(module)
    list_html = _get_templates().TemplateResponse(
        "partials/list_wrapper.html",
        {
            "request": request, "cfg": cfg, "module": module,
            "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
            "content_template": f"partials/lists/{module}.html",
            "running": get_running(),
        },
    ).body.decode()

    open_modal_js = (
        f'<script>(function(){{'
        f'fetch("/api/run/{module}/{item_id}/logs?live=1")'
        f'.then(r=>r.text())'
        f'.then(html=>{{document.body.insertAdjacentHTML("beforeend",html)}});'
        f'}})();</script>'
    )
    return HTMLResponse(list_html + open_modal_js)


# ── Ganzes Modul ausführen ────────────────────────────────────────

@router.post("/{module}", response_class=HTMLResponse)
def run_module(module: str, request: Request, debug: bool = False):
    run_id = MODULE_DEBUG_ID if debug else MODULE_RUN_ID
    key = f"{module}:{run_id}"
    if key in _running:
        raise HTTPException(status_code=409, detail="Modul läuft bereits")

    def _execute():
        set_debug(debug)
        _mark_running(module, run_id, "debug" if debug else "run")
        # Tee-Context: alle Einzellogs werden auch ins Modul-Log gespiegelt
        set_tee_context(module, run_id)
        try:
            _dispatch_module(module)
        finally:
            clear_tee_context()
            _mark_done(module, run_id)
            set_debug(False)

    threading.Thread(target=_execute, daemon=True).start()

    cfg = load_config(module)
    list_html = _get_templates().TemplateResponse(
        "partials/list_wrapper.html",
        {
            "request": request, "cfg": cfg, "module": module,
            "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
            "content_template": f"partials/lists/{module}.html",
            "running": get_running(),
        },
    ).body.decode()

    # Log-Modal für den Modul-Gesamt-Run öffnen
    open_modal_js = (
        f'<script>(function(){{'
        f'fetch("/api/run/{module}/{run_id}/logs?live=1")'
        f'.then(r=>r.text())'
        f'.then(html=>{{document.body.insertAdjacentHTML("beforeend",html)}});'
        f'}})();</script>'
    )
    return HTMLResponse(list_html + open_modal_js)


# ── SSE: Live-Log-Stream ──────────────────────────────────────────

@router.get("/{module}/{item_id}/logs/stream")
async def stream_log(module: str, item_id: str):
    async def event_generator():
        lp = log_path(module, item_id)
        waited = 0
        while not lp.exists() and waited < 10:
            await asyncio.sleep(0.3)
            waited += 0.3
            lp = log_path(module, item_id)

        if not lp.exists():
            yield "event: done\ndata: \n\n"
            return

        sent_lines = 0
        idle_after_done = 0

        while True:
            lines = []
            try:
                with lp.open("r", encoding="utf-8") as f:
                    lines = [l.rstrip() for l in f.readlines()]
            except OSError:
                pass

            for line in lines[sent_lines:]:
                if not line:
                    continue
                level = "info"
                if "WARNING:" in line: level = "warning"
                elif "ERROR:"   in line: level = "error"
                elif "DEBUG:"   in line: level = "debug"
                safe = line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                html = f'<div class="log-line log-{level}">{safe}</div>'
                yield f"data: {html}\n\n"
            sent_lines = len(lines)

            running = _is_running(module, item_id)
            if not running:
                idle_after_done += 0.5
                if idle_after_done >= 3:
                    yield "event: done\ndata: \n\n"
                    return
            else:
                idle_after_done = 0

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Log-Endpunkte ─────────────────────────────────────────────────

@router.get("/{module}/{item_id}/logs", response_class=HTMLResponse)
def get_item_logs(module: str, item_id: str, request: Request, live: int = 0):
    dates = get_log_dates(module, item_id)
    selected = dates[0] if dates else None
    lines = read_log(module, item_id, selected) if selected else []
    description = _item_description(module, item_id)
    return _get_templates().TemplateResponse(
        "partials/log_modal.html",
        {
            "request": request, "module": module, "item_id": item_id,
            "description": description,
            "dates": dates, "selected": selected, "lines": lines,
            "live": bool(live),
        },
    )

@router.get("/{module}/{item_id}/logs/{date}", response_class=HTMLResponse)
def get_item_log_by_date(module: str, item_id: str, date: str, request: Request):
    lines = read_log(module, item_id, date)
    return _get_templates().TemplateResponse(
        "partials/log_content.html",
        {"request": request, "lines": lines, "date": date},
    )

@router.get("/errors", response_class=HTMLResponse)
def get_errors(request: Request):
    return _get_templates().TemplateResponse(
        "partials/errors/error_list.html",
        {"request": request, "errors": get_all_errors(days=14)},
    )


# ── Hilfsfunktionen ───────────────────────────────────────────────

def _item_description(module: str, item_id: str) -> str:
    if item_id == MODULE_RUN_ID:
        return f"{module.replace('_', ' ').title()} – Gesamt-Run"
    if item_id == MODULE_DEBUG_ID:
        return f"{module.replace('_', ' ').title()} – Debug-Run"
    try:
        cfg = load_config(module)
        raw = cfg.get(item_id) or cfg.get(
            int(item_id) if str(item_id).isdigit() else item_id) or {}
        return raw.get("description", item_id)
    except Exception:
        return item_id


def _dispatch_single(module: str, item_id: str) -> None:
    if module == "borg":
        from modules.borg import run_single
        run_single(item_id)
    elif module == "rsync":
        from modules.rsync import run_single
        run_single(item_id)
    elif module == "proxmox_lxc":
        from modules.proxmox_lxc import run_single
        run_single(item_id)
    elif module == "proxmox_hosts":
        from modules.proxmox_hosts import run_single
        run_single(item_id)
    elif module == "proxmox_jobs":
        from modules.proxmox_jobs import run_single
        run_single(item_id)
    else:
        from helpers.logger import log
        log("ERROR", f"Unbekanntes Modul: {module}")


def _dispatch_module(module: str) -> None:
    if module == "borg":
        from modules.borg import run
        run()
    elif module == "rsync":
        from modules.rsync import run
        run()
    elif module in ("proxmox_lxc", "proxmox_hosts", "proxmox_jobs"):
        from modules import proxmox
        # Nur das jeweilige Sub-Modul ausführen
        if module == "proxmox_lxc":
            from modules.proxmox_lxc import run
        elif module == "proxmox_hosts":
            from modules.proxmox_hosts import run
        else:
            from modules.proxmox_jobs import run
        run()
