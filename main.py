# main.py
from pathlib import Path
import yaml
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.wsgi import WSGIMiddleware
import uvicorn

from flask import Flask, render_template, send_from_directory, abort

# -------------------------
# Projektpfade
# -------------------------
ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
CONFIG_DIR = ROOT / "config"

# -------------------------
# Hilfsfunktionen
# -------------------------
def load_yaml(path: Path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        logging.exception("Fehler beim Laden von YAML: %s", path)
        return {}

# -------------------------
# Flask UI App (exportiert app)
# -------------------------
flask_app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static"
)

@flask_app.context_processor
def inject_common():
    # Globale Template-Variablen (kann erweitert werden)
    return {"app_name": "backupctl"}

# Root UI (Standard: Borg tab)
@flask_app.route("/")
def index():
    return render_template("index.html",
                           user="ottoadm",
                           active_tab="borg",
                           initial_content_url="/api/tabs/borg")

# Top-level UI routes so direct URLs work (Variante A)
@flask_app.route("/borg")
def page_borg():
    return render_template("index.html",
                           user="ottoadm",
                           active_tab="borg",
                           initial_content_url="/api/tabs/borg")

@flask_app.route("/proxmox", defaults={"subpath": ""})
@flask_app.route("/proxmox/<path:subpath>")
def page_proxmox_sub(subpath: str):
    """
    Liefert die UI-Shell für /proxmox und alle Unterpfade.
    Bestimmt initial_content_url anhand des Unterpfads.
    """
    # Normalisiere Pfad
    key = subpath.strip("/").lower()

    # Mapping Unterpfad -> api/tabs URL
    mapping = {
        "": "/api/tabs/proxmox/jobs",        # /proxmox -> jobs standard
        "jobs": "/api/tabs/proxmox/jobs",
        "lxc": "/api/tabs/proxmox/lxc",
        "hosts": "/api/tabs/proxmox/hosts",
    }

    initial = mapping.get(key, "/api/tabs/proxmox/jobs")  # default fallback
    return render_template("index.html",
                           user="ottoadm",
                           active_tab="proxmox",
                           initial_content_url=initial)


@flask_app.route("/rsync")
def page_rsync():
    return render_template("index.html",
                           user="ottoadm",
                           active_tab="rsync",
                           initial_content_url="/api/tabs/rsync")

# # HTMX partial: Borg list (backwards compatibility, optional)
# @flask_app.route("/borg/list")
# def borg_list():
#     cfg = load_yaml(CONFIG_DIR / "borg.yaml")
#     # _borg_list.html sollte ein wrapper-element mit data-active="borg" enthalten
#     return render_template("_borg_list.html", jobs=cfg)

# # HTMX partial: Proxmox list (Platzhalter)
# @flask_app.route("/proxmox/list")
# def proxmox_list():
#     return render_template("_empty_section.html",
#                            title="Proxmox",
#                            message="Proxmox placeholder",
#                            data_active="proxmox")

# # HTMX partial: Rsync list (Platzhalter)
# @flask_app.route("/rsync/list")
# def rsync_list():
#     return render_template("_empty_section.html",
#                            title="Rsync",
#                            message="Rsync placeholder",
#                            data_active="rsync")

# Optional: favicon (falls nicht in /static automatisch)
@flask_app.route("/favicon.ico")
def favicon():
    fav_dir = STATIC_DIR / "favicon"
    if (fav_dir / "favicon-32x32.png").exists():
        return send_from_directory(str(fav_dir), "favicon-32x32.png")
    abort(404)

# -------------------------
# FastAPI App (API + Static mount + WSGI mount)
# -------------------------
# Setze docs- und openapi-URLs unter /api
app = FastAPI(
    title="backupctl API + UI",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# 1) StaticFiles mount muss VOR dem WSGI-Mount stehen
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 2) API-Router einbinden (muss VOR dem WSGI-Mount passieren)
try:
    # from api.routers import borg as borg_router
    # from api.routers import proxmox as proxmox_router
    # from api.routers import rsync as rsync_router
    from api.routers import tabs as tabs_router
    from api.routers.config import config_router

    # app.include_router(borg_router.router, prefix="/api", tags=["borg"])
    # app.include_router(proxmox_router.router, prefix="/api", tags=["proxmox"])
    # app.include_router(rsync_router.router, prefix="/api", tags=["rsync"])
    app.include_router(tabs_router.router)  # bindet /api/tabs/*

    resources = [ "borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync", ]
    for name in resources: 
        router = config_router(name, tag=name) 
        app.include_router(router, prefix=f"/api/config/{name}")

except Exception:
    logging.exception("API-Router konnten nicht eingebunden werden. Prüfe api/routers/*")

# 3) /api root: Redirect auf /api/docs (oder gib Info zurück)
@app.get("/api")
def api_root():
    # Redirect zur Swagger UI
    return RedirectResponse(url="/api/docs")

# 4) Kleiner health endpoint unter /api
@app.get("/api/health")
def health():
    return {"status": "ok"}

# 5) Mount Flask UI unter Root (als letztes)
app.mount("/", WSGIMiddleware(flask_app))

# -------------------------
# CLI / Debug Start
# -------------------------
if __name__ == "__main__":
    # Für Entwicklung: uvicorn startet die kombinierte App
    uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=True)
