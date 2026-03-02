from fastapi import FastAPI
from api.custom_swagger import router as swagger_router
from api.routers import ui as tabs_router
from api.routers.config import config_router
from api.routers.run import router as run_router
from api.routers.settings import router as settings_router
from api.routers.repos import router as repos_router
from api.routers.browser import router as browser_router
from api.routers.stats import router as stats_router
from api.routers.sysinfo import router as sysinfo_router
from api.routers.history import router as history_router

def create():
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json"
    )

    from api.storage import init_db
    init_db()

    from settings import LIGHT_MODE
    if not LIGHT_MODE:
        from scheduler.engine import init_scheduler
        init_scheduler()

    # Custom Swagger UI
    app.include_router(swagger_router)

    # HTML/Tabs unter /api/ui/*
    app.include_router(tabs_router.router, prefix="/ui")

    # Config-Router unter /api/config/<module>/*
    resources = ["borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"]
    for name in resources:
        router = config_router(name, tag=name)
        app.include_router(router, prefix=f"/config/{name}")
        from api.routers.config import enable_disable_router
        app.include_router(enable_disable_router(name), prefix=f"/config/{name}")

    app.include_router(run_router, prefix="/run")
    app.include_router(settings_router, prefix="/settings")
    app.include_router(repos_router, prefix="/repos")
    app.include_router(browser_router, prefix="/browser")
    app.include_router(stats_router, prefix="/stats")
    app.include_router(sysinfo_router, prefix="/sysinfo")
    app.include_router(history_router, prefix="/history")

    return app
