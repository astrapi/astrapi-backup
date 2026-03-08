"""
backupctl – Einstiegspunkt (FastAPI + Flask)

FastAPI  → /api/...       JSON-Endpunkte, OpenAPI, Swagger
Flask    → /              UI, HTMX-Partials, Modals

Start:
    python main.py              # Port 5001 (Standard)
    python main.py --port 8080
    python main.py --no-reload  # ohne File-Watcher
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT     = PROJECT_ROOT / "app"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware
import uvicorn

from core.ui import create as create_ui
from core.system.health import register_health
from core.system.systemd import sd_notify, start_watchdog
from core.modules.settings.engine import configure as configure_settings
from core.modules.scheduler.engine import configure as configure_scheduler, init as init_scheduler
from api.fastapi_app import create as create_api
from api.storage import get_setting, set_setting
from app.runner import run_backup

_START_TIME = time.time()


def _db_check() -> tuple[bool, dict]:
    from api.storage import _conn
    try:
        _conn().execute("SELECT 1").fetchone()
        return True, {"db": True}
    except Exception:
        return False, {"db": False}


def create_app() -> FastAPI:
    configure_settings(health_fn=_db_check)
    configure_scheduler(
        job_fn=run_backup,
        get_setting=get_setting,
        set_setting=set_setting,
        job_id="backup",
        job_name="Backup",
        job_kwargs={"job_id": "backup", "modules": [], "debug": False},
        timezone="Europe/Berlin",
    )

    api = create_api()
    ui  = create_ui(app_root=APP_ROOT)

    core_static = PROJECT_ROOT / "core" / "ui" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/api", api)
    api.mount("/", WSGIMiddleware(ui))

    register_health(api, check_fn=_db_check, start_time=_START_TIME)
    init_scheduler()
    start_watchdog(check_fn=lambda: _db_check()[0])
    sd_notify("READY=1")
    return api


app = create_app()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-reload", dest="reload", action="store_false", default=True)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
