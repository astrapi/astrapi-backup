# api/routers/run.py
import asyncio
import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from helpers.logger import (get_log_dates, read_log,
                             log_path, set_tee_context, clear_tee_context,
                             set_log_context, clear_log_context)
from api.storage import load_config

ROOT = Path(__file__).resolve().parents[2]
_templates = None


def _get_templates():
    global _templates
    if _templates is None:
        from api.templates import templates as t
        _templates = t
    return _templates


_running: dict = {}
_running_lock  = threading.Lock()

MODULE_RUN_ID   = "__run__"
MODULE_DEBUG_ID = "__debug__"


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


def make_run_router(module: str) -> APIRouter:
    """Erzeugt einen APIRouter mit Run/Log-Routen für ein einzelnes Modul.

    Einbinden mit prefix=f"/{module}" → externe URLs:
      POST /api/{module}/{item_id}/run
      POST /api/{module}/run
      GET  /api/{module}/status
      GET  /api/{module}/{item_id}/logs
      GET  /api/{module}/{item_id}/logs/stream
      GET  /api/{module}/{item_id}/logs/{date}
    """
    router = APIRouter(tags=[module])

    # ── Status-Endpunkt für Badge-Refresh ────────────────────────────

    @router.get("/status", response_class=HTMLResponse)
    def module_status(request: Request):
        cfg = load_config(module)
        return _get_templates().TemplateResponse(
            "partials/list_wrapper_inner.html",
            {
                "request": request, "cfg": cfg, "module": module,
                "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
                "content_template": f"{module}/partials/list.html",
                "running": get_running(),
            },
        )

    # ── Einzelnen Eintrag ausführen ───────────────────────────────────

    @router.post("/{item_id}/run", response_class=HTMLResponse)
    def run_item(item_id: str, request: Request, debug: bool = False):
        if _is_running(module, item_id):
            raise HTTPException(status_code=409, detail="Läuft bereits")

        _mark_running(module, item_id, "debug" if debug else "run")

        log_id = f"{item_id}_debug" if debug else item_id

        def _execute():
            import time
            from api.storage import history_start, history_finish
            desc = _item_description(module, item_id)
            hist_id = history_start(module, item_id, desc, "debug" if debug else "run")
            t0 = time.time()
            set_tee_context(module, log_id)
            status = "ok"
            try:
                _dispatch_single(module, item_id)
            except Exception:
                status = "error"
            finally:
                duration = int(time.time() - t0)
                history_finish(hist_id, status, duration)
                clear_tee_context()
                _mark_done(module, item_id)

        threading.Thread(target=_execute, daemon=True).start()

        cfg = load_config(module)
        list_html = _get_templates().TemplateResponse(
            "partials/list_wrapper_inner.html",
            {
                "request": request, "cfg": cfg, "module": module,
                "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
                "content_template": f"{module}/partials/list.html",
                "running": get_running(),
            },
        ).body.decode()

        trigger = json.dumps({"openLogModal": {"module": module, "itemId": log_id}})
        return HTMLResponse(list_html, headers={"HX-Trigger": trigger})

    # ── Ganzes Modul ausführen ────────────────────────────────────────

    @router.post("/run", response_class=HTMLResponse)
    def run_all(request: Request, debug: bool = False):
        run_id = MODULE_DEBUG_ID if debug else MODULE_RUN_ID

        if _is_running(module, run_id):
            raise HTTPException(status_code=409, detail="Modul läuft bereits")

        _mark_running(module, run_id, "debug" if debug else "run")

        def _execute():
            import time
            from api.storage import history_start, history_finish
            desc = _item_description(module, run_id)
            hist_id = history_start(module, run_id, desc, "debug" if debug else "run")
            t0 = time.time()
            set_log_context(module, run_id)
            set_tee_context(module, run_id)
            status = "ok"
            try:
                _dispatch_module(module)
            except Exception:
                status = "error"
            finally:
                duration = int(time.time() - t0)
                history_finish(hist_id, status, duration)
                clear_tee_context()
                clear_log_context()
                _mark_done(module, run_id)

        threading.Thread(target=_execute, daemon=True).start()

        cfg = load_config(module)
        list_html = _get_templates().TemplateResponse(
            "partials/list_wrapper_inner.html",
            {
                "request": request, "cfg": cfg, "module": module,
                "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
                "content_template": f"{module}/partials/list.html",
                "running": get_running(),
            },
        ).body.decode()

        trigger = json.dumps({"openLogModal": {"module": module, "itemId": run_id}})
        return HTMLResponse(list_html, headers={"HX-Trigger": trigger})

    # ── SSE: Live-Log-Stream ──────────────────────────────────────────

    @router.get("/{item_id}/logs/stream")
    async def stream_log_ep(item_id: str):
        async def event_generator():
            lp = log_path(module, item_id)
            waited = 0.0
            while not lp.exists() and waited < 15:
                await asyncio.sleep(0.3)
                waited += 0.3
                lp = log_path(module, item_id)

            if not lp.exists():
                yield "event: done\ndata: \n\n"
                return

            sent_lines      = 0
            idle_after_done = 0.0

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
                    safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    yield f"data: <div class=\"log-line log-{level}\">{safe}</div>\n\n"
                sent_lines = len(lines)

                running_key = item_id.removesuffix("_debug") if item_id.endswith("_debug") else item_id
                still_running = _is_running(module, running_key) or _is_running(module, item_id)

                if not still_running:
                    idle_after_done += 0.5
                    if idle_after_done >= 3:
                        yield "event: done\ndata: \n\n"
                        return
                else:
                    idle_after_done = 0.0

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Log-Endpunkte ─────────────────────────────────────────────────

    @router.get("/{item_id}/logs", response_class=HTMLResponse)
    def get_logs(item_id: str, request: Request, live: int = 0):
        dates    = get_log_dates(module, item_id)
        selected = dates[0] if dates else None
        lines    = read_log(module, item_id, selected) if selected else []
        return _get_templates().TemplateResponse(
            "partials/log_modal.html",
            {
                "request": request, "module": module, "item_id": item_id,
                "description": _item_description(module, item_id),
                "dates": dates, "selected": selected, "lines": lines,
                "live": bool(live),
            },
        )

    @router.get("/{item_id}/logs/{date}", response_class=HTMLResponse)
    def get_log_by_date(item_id: str, date: str, request: Request):
        return _get_templates().TemplateResponse(
            "partials/log_content.html",
            {"request": request, "lines": read_log(module, item_id, date), "date": date},
        )

    return router


# ── Hilfsfunktionen ───────────────────────────────────────────────

def _item_description(module: str, item_id: str) -> str:
    if item_id == MODULE_RUN_ID:
        return f"{module.replace('_', ' ').title()} – Gesamt-Run"
    if item_id == MODULE_DEBUG_ID:
        return f"{module.replace('_', ' ').title()} – Debug-Run"
    debug = item_id.endswith("_debug")
    base  = item_id.removesuffix("_debug")
    try:
        cfg = load_config(module)
        raw = cfg.get(base) or cfg.get(int(base) if base.isdigit() else base) or {}
        desc = raw.get("description", base)
        return f"{desc} (Debug)" if debug else desc
    except Exception:
        return item_id


def _dispatch_single(module: str, item_id: str) -> None:
    fn = {
        "borg":          lambda: __import__("modules.borg",          fromlist=["run_single"]).run_single(item_id),
        "rsync":         lambda: __import__("modules.rsync",         fromlist=["run_single"]).run_single(item_id),
        "proxmox_lxc":   lambda: __import__("modules.proxmox_lxc",   fromlist=["run_single"]).run_single(item_id),
        "proxmox_hosts": lambda: __import__("modules.proxmox_hosts", fromlist=["run_single"]).run_single(item_id),
        "proxmox_jobs":  lambda: __import__("modules.proxmox_jobs",  fromlist=["run_single"]).run_single(item_id),
    }.get(module)
    if fn:
        fn()
    else:
        from helpers.logger import log
        log("ERROR", f"Unbekanntes Modul: {module}")


def _dispatch_module(module: str) -> None:
    fn = {
        "borg":          lambda: __import__("modules.borg",          fromlist=["run"]).run(),
        "rsync":         lambda: __import__("modules.rsync",         fromlist=["run"]).run(),
        "proxmox_lxc":   lambda: __import__("modules.proxmox_lxc",   fromlist=["run"]).run(),
        "proxmox_hosts": lambda: __import__("modules.proxmox_hosts", fromlist=["run"]).run(),
        "proxmox_jobs":  lambda: __import__("modules.proxmox_jobs",  fromlist=["run"]).run(),
    }.get(module)
    if fn:
        fn()
