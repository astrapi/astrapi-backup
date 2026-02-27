from fastapi import FastAPI
from api.custom_swagger import router as swagger_router
from api.routers import ui as tabs_router
from api.routers.config import config_router
from api.routers.run import router as run_router
from api.routers.scheduler import router as scheduler_router

def create():
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json"
    )

    from api.storage import init_db
    init_db()

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

    app.include_router(run_router, prefix="/run")
    app.include_router(scheduler_router, prefix="/scheduler")

    print("Registered routes:")
    for route in app.routes:
        print(route.path, route.name)

    return app
