# api/routers/run.py
import asyncio
import json
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from astrapi.core.system.logger import set_tee_context, clear_tee_context, set_active_log_id, clear_active_log_id
from astrapi.core.system.activity_log import (
    history_start, history_finish,
    get_log_lines, get_latest_activity_log_id, list_runs_for_item,
)
from backupctl.api.storage import load_config

_templates = None


def _get_templates():
    global _templates
    if _templates is None:
        from backupctl.api.templates import templates as t
        _templates = t
    return _templates


_running: dict = {}
_running_lock  = threading.Lock()


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
      GET  /api/{module}/{item_id}/logs/{log_id}
    """
    router = APIRouter(tags=[module])

    # ── Status-Endpunkt für Badge-Refresh ────────────────────────────

    @router.get("/status", response_class=HTMLResponse)
    def module_status(request: Request):
        cfg = load_config(module)
        return _get_templates().TemplateResponse(
            request,
            "partials/list_wrapper_inner.html",
            {
                "cfg": cfg, "module": module,
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
            desc    = _item_description(module, item_id)
            hist_id = history_start(module, item_id, desc, "debug" if debug else "run")
            t0      = time.time()
            set_tee_context(module, log_id)
            set_active_log_id(hist_id)
            status = "ok"
            try:
                _dispatch_single(module, item_id)
            except Exception:
                status = "error"
            finally:
                duration = int(time.time() - t0)
                # Status aus Log-Zeilen ableiten falls kein Exception-Fehler
                if status == "ok":
                    levels = {r["level"] for r in get_log_lines(hist_id)}
                    if "ERROR" in levels:
                        status = "error"
                    elif "WARNING" in levels:
                        status = "warning"
                history_finish(hist_id, status, duration)
                clear_active_log_id()
                clear_tee_context()
                _mark_done(module, item_id)
                if not debug:
                    from astrapi.core.modules.scheduler.job_runner import _notify
                    _notify(module, desc, status, duration)

        threading.Thread(target=_execute, daemon=True).start()

        cfg = load_config(module)
        list_html = _get_templates().TemplateResponse(
            request,
            "partials/list_wrapper_inner.html",
            {
                "cfg": cfg, "module": module,
                "container_id": f"tab-{module}", "loading_id": f"{module}-loading",
                "content_template": f"{module}/partials/list.html",
                "running": get_running(),
            },
        ).body.decode()

        trigger = json.dumps({"openLogModal": {"module": module, "itemId": log_id}})
        return HTMLResponse(list_html, headers={"HX-Trigger": trigger})

    # ── SSE: Live-Log-Stream (DB-basiert) ─────────────────────────────

    @router.get("/{item_id}/logs/stream")
    async def stream_log_ep(item_id: str):
        async def event_generator():

            # Warte bis activity_log-Eintrag existiert (Job startet im Thread)
            act_log_id = None
            waited     = 0.0
            while act_log_id is None and waited < 15:
                act_log_id = get_latest_activity_log_id(module, item_id)
                if act_log_id is None:
                    await asyncio.sleep(0.3)
                    waited += 0.3

            if act_log_id is None:
                yield "event: done\ndata: \n\n"
                return

            last_id        = 0
            idle_after_done = 0.0

            while True:
                rows = get_log_lines(act_log_id, after_id=last_id)
                for row in rows:
                    last_id = row["id"]
                    level   = row["level"].lower()
                    safe    = (row["line"]
                               .replace("&", "&amp;")
                               .replace("<", "&lt;")
                               .replace(">", "&gt;"))
                    yield f"data: <div class=\"log-line log-{level}\">{safe}</div>\n\n"

                running_key  = item_id.removesuffix("_debug") if item_id.endswith("_debug") else item_id
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

    # ── Log-Endpunkte (DB-basiert) ────────────────────────────────────

    @router.get("/{item_id}/logs", response_class=HTMLResponse)
    def get_logs(item_id: str, request: Request, live: int = 0):
        runs       = list_runs_for_item(module, item_id)
        act_log_id = runs[0]["id"] if runs else None
        lines      = [r["line"] for r in get_log_lines(act_log_id)] if act_log_id else []

        # "dates" = Liste von Runs für den Datum-Wähler im Modal
        dates    = [{"id": str(r["id"]), "label": r["started_at"] or str(r["id"])} for r in runs]
        selected = str(act_log_id) if act_log_id else None

        return _get_templates().TemplateResponse(
            request,
            "partials/log_modal.html",
            {
                "module": module, "item_id": item_id,
                "description": _item_description(module, item_id),
                "dates": dates, "selected": selected, "lines": lines,
                "live": bool(live),
            },
        )

    @router.get("/{item_id}/logs/{log_id}", response_class=HTMLResponse)
    def get_log_by_id(item_id: str, log_id: str, request: Request):
        lines = [r["line"] for r in get_log_lines(int(log_id))] if log_id.isdigit() else []
        return _get_templates().TemplateResponse(
            request,
            "partials/log_content.html",
            {"lines": lines, "date": log_id},
        )

    return router


# ── Hilfsfunktionen ───────────────────────────────────────────────

def _item_description(module: str, item_id: str) -> str:
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
    import importlib
    try:
        mod = importlib.import_module(f"backupctl.modules.{module}.jobs")
    except ModuleNotFoundError:
        from astrapi.core.system.logger import log
        log("ERROR", f"Unbekanntes Modul: {module}")
        return
    mod.run_single(item_id)
