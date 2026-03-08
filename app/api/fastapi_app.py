"""
app/api/fastapi_app.py  –  FastAPI-Factory für backupctl

Registriert automatisch alle Modul-Router aus app/modules/
sowie die backupctl-spezifische Infrastruktur (run, settings, swagger).
"""
from pathlib import Path
from fastapi import FastAPI

APP_ROOT = Path(__file__).resolve().parents[1]   # = app/


def create() -> FastAPI:
    app = FastAPI(
        title="BackupCtl API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    from api.storage import init_db
    init_db()

    import yaml as _yaml
    _cfg_yaml = APP_ROOT / "config.yaml"
    _light_mode = False
    if _cfg_yaml.exists():
        with open(_cfg_yaml, encoding="utf-8") as _f:
            _light_mode = bool((_yaml.safe_load(_f) or {}).get("app", {}).get("light_mode", False))
    # ── Custom Swagger UI ──────────────────────────────────────────────────────
    from api.custom_swagger import router as swagger_router
    app.include_router(swagger_router)

    # ── Modul-Router automatisch registrieren ─────────────────────────────────
    # Jedes modules/<name>/api.py liefert einen FastAPI-Router.
    # Da die FastAPI-App unter /api gemountet ist (main.py), werden die Router
    # ohne /api-Prefix eingebunden → extern erreichbar als /api/<key>/...
    from core.ui.module_registry import load_modules
    modules = load_modules(APP_ROOT)
    for mod in modules:
        if mod.api_router is not None:
            app.include_router(
                mod.api_router,
                prefix=f"/{mod.key}",
                tags=[mod.key],
            )

    # ── Run/Log-Router pro Modul (Framework-Standard: /api/{module}/{item}/run) ─
    from api.routers.run import make_run_router
    _RUN_MODULES = ["borg", "rsync", "proxmox_lxc", "proxmox_hosts", "proxmox_jobs"]
    for _mod_key in _RUN_MODULES:
        app.include_router(make_run_router(_mod_key), prefix=f"/{_mod_key}")

    from api.routers.settings import router as settings_router
    app.include_router(settings_router, prefix="/settings")

    return app
