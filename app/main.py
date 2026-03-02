# app/main.py
import sys
from pathlib import Path

# core/ liegt eine Ebene über app/ → ins sys.path damit "from core.ui import ..." funktioniert
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware

from core.ui import create as create_ui
from api.app import create as create_api
from scheduler.engine import init_scheduler

import uvicorn
import time
import threading
from fastapi import Response

APP_ROOT = Path(__file__).resolve().parent  # = app/


_START_TIME = time.time()


def create_app():
    api = create_api()
    ui  = create_ui(app_root=APP_ROOT, extra_init=_register_backupctl_routes)

    app = api
    core_static = _PROJECT_ROOT / "core" / "static"
    app.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    app.mount("/api", api)
    app.mount("/", WSGIMiddleware(ui))

    _register_health(app)
    init_scheduler()
    _migrate_secrets()   # ← MIGRATIONS-AUFRUF: nach Migration entfernbar (siehe helpers/secrets.py)
    _start_watchdog()
    _sd_notify("READY=1")
    return app


def _register_health(app):
    """GET /health – für systemd, Uptime-Kuma, etc."""
    @app.get("/health", include_in_schema=False)
    def health():
        from api.storage import _conn
        try:
            _conn().execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            db_ok = False
        uptime = int(time.time() - _START_TIME)
        status = 200 if db_ok else 503
        return Response(
            content=f'{{"status":{"ok" if db_ok else "degraded"},"uptime_s":{uptime},"db":{str(db_ok).lower()}}}',
            media_type="application/json",
            status_code=status,
        )


def _sd_notify(msg: str) -> None:
    """Sendet eine Nachricht an systemd (sd_notify) falls verfügbar."""
    try:
        import socket, os
        sock_path = os.environ.get("NOTIFY_SOCKET", "")
        if not sock_path:
            return
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(sock_path)
            s.sendall(msg.encode())
    except Exception:
        pass


def _start_watchdog() -> None:
    """
    Sendet alle 20s WATCHDOG=1 an systemd solange der Health-Check besteht.
    WatchdogSec=60s in der Unit → zwei verpasste Pings → Neustart.
    """
    import os
    if not os.environ.get("NOTIFY_SOCKET"):
        return   # nicht unter systemd → kein Watchdog nötig

    def _ping():
        from api.storage import _conn
        while True:
            time.sleep(20)
            try:
                _conn().execute("SELECT 1").fetchone()
                _sd_notify("WATCHDOG=1")
            except Exception:
                pass   # kein Ping → systemd startet nach WatchdogSec neu

    t = threading.Thread(target=_ping, daemon=True, name="watchdog")
    t.start()


def _migrate_secrets():
    # ← MIGRATIONS-BLOCK: nach Migration entfernbar
    try:
        from helpers.secrets import migrate_from_env_file
        migrated = migrate_from_env_file()
        if migrated:
            print(f"[secrets] Migration aus secrets.env abgeschlossen: {migrated}")
            print("[secrets] secrets.env kann nun gelöscht werden.")
    except Exception as e:
        print(f"[secrets] Migrations-Fehler (nicht kritisch): {e}")
    # ← Ende Migrations-Block


def _register_backupctl_routes(flask_app):
    """Registriert backupctl-spezifische UI-Routen (Modals, Scheduler)."""
    from ui.modal_routes import register_modal_routes
    register_modal_routes(flask_app)


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9999, reload=True)
