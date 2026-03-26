"""
app/api/fastapi_app.py  –  FastAPI-Factory für backupctl

Registriert automatisch alle Modul-Router aus app/modules/
sowie die backupctl-spezifische Infrastruktur (run/log-streaming).
"""
from pathlib import Path
from fastapi import FastAPI
from astrapi.core.system.version import get_app_version

APP_ROOT = Path(__file__).resolve().parents[1]   # = app/


def create(modules: list | None = None) -> FastAPI:
    """Erstellt die FastAPI-Anwendung.

    modules: Vorgeladene Modulliste (z.B. aus main.py). Wird nicht neu geladen
             wenn angegeben – verhindert doppelten Modulaufruf.
    """
    _version = get_app_version(APP_ROOT, default="1.0.0")
    app = FastAPI(
        title="BackupCtl API",
        version=_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    from astrapi.core.system.logger import configure_log_root
    configure_log_root(APP_ROOT / "logs")

    from astrapi.core.system.secrets import configure as configure_secrets
    configure_secrets(
        key_path     = Path("/var/lib/backupadm/secret.key"),
        dev_key_path = APP_ROOT / "config" / "secret.key",
    )

    # ── Modul-Router registrieren (nur laden wenn nicht übergeben) ────────────────────
    from astrapi.core.ui.module_registry import load_modules, register_fastapi_modules
    if modules is None:
        modules = load_modules(APP_ROOT)
    register_fastapi_modules(app, modules)

    # ── Run/Log-Router pro Modul (Framework-Standard: /api/{module}/{item}/run) ─
    from api.routers.run import make_run_router
    _RUN_MODULES = ["borg", "rsync", "proxmox_lxc", "proxmox_hosts", "proxmox_jobs"]
    for _mod_key in _RUN_MODULES:
        app.include_router(make_run_router(_mod_key), prefix=f"/api/{_mod_key}")

    return app
