#api/app.py
from fastapi import FastAPI
from api.routers import html as tabs_router
from api.routers.config import config_router

def create():
    app = FastAPI()
    # app = FastAPI(
    #     title="backupctl API",
    #     docs_url="/docs",
    #     redoc_url="/redoc",
    #     openapi_url="/openapi.json"
    # )

    # HTML/Tabs unter /api/html/*
    app.include_router(tabs_router.router, prefix="/html")

    # Config-Router unter /api/config/<module>/*
    resources = ["borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"]
    for name in resources:
        router = config_router(name, tag=name)
        app.include_router(router, prefix=f"/config/{name}")

    return app
