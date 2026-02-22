from fastapi import FastAPI
from api.custom_swagger import router as swagger_router
from api.routers import ui as tabs_router
from api.routers.config import config_router

def create():
    app = FastAPI(
        docs_url=None,          # eingebaute Swagger-UI deaktivieren
        redoc_url=None,         # ReDoc deaktivieren
        openapi_url="/api/openapi.json"  # wichtig!
    )

    # Custom Swagger UI
    app.include_router(swagger_router)

    # HTML/Tabs unter /api/ui/*
    app.include_router(tabs_router.router, prefix="/ui")

    # Config-Router unter /api/config/<module>/*
    resources = ["borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"]
    for name in resources:
        router = config_router(name, tag=name)
        app.include_router(router, prefix=f"/config/{name}")

    print("Registered routes:")
    for route in app.routes:
        print(route.path, route.name)

    return app
