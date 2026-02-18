# main.py
from pathlib import Path
import os
import yaml
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.wsgi import WSGIMiddleware
import uvicorn

from flask import Flask, render_template, send_from_directory, abort, url_for, request

# -------------------------
# Projektpfade
# -------------------------
ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
CONFIG_DIR = ROOT / "config"
NAV_YAML_PATH = os.path.join(os.path.dirname(__file__), "templates", "navigation", "items.yaml")

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

flask_app.config.update(
    DEBUG=True,
    TEMPLATES_AUTO_RELOAD=True,
    SEND_FILE_MAX_AGE_DEFAULT=0
)


@flask_app.context_processor
def inject_common():
    # Globale Template-Variablen (kann erweitert werden)
    return {"app_name": "backupctl"}

# Root UI (Standard: Borg tab)
# @flask_app.route("/")
# def index():
#     return render_template("index.html",user="ottoadm",active_tab="borg",initial_content_url="/api/html/borg")

# # Top-level UI routes so direct URLs work (Variante A)
# @flask_app.route("/borg")
# def page_borg():
#     return render_template("index.html",user="ottoadm",active_tab="borg",initial_content_url="/api/html/borg")

# @flask_app.route("/proxmox_jobs")
# def page_proxmox_jobs():
#     return render_template("index.html",user="ottoadm",active_tab="proxmox_jobs",initial_content_url="/api/html/proxmox_jobs")

# @flask_app.route("/proxmox_hosts")
# def page_proxmox_hosts():
#     return render_template("index.html",user="ottoadm",active_tab="proxmox_hosts",initial_content_url="/api/html/proxmox_hosts")

# @flask_app.route("/proxmox_lxc")
# def page_proxmox_lxc():
#     return render_template("index.html",user="ottoadm",active_tab="proxmox_lxc",initial_content_url="/api/html/proxmox_lxc")

# @flask_app.route("/rsync")
# def page_rsync():
#     return render_template("index.html",user="ottoadm",active_tab="rsync",initial_content_url="/api/html/rsync")

# app.py oder routes.py
# routes.py

#app = Flask(__name__)

def load_nav(path=NAV_YAML_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
    except FileNotFoundError:
        raise RuntimeError(f"Navigation file not found: {path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Error parsing navigation YAML: {e}")

    items = []
    defaults = []
    for entry in raw:
        k = entry.get("key")
        if not k:
            continue
        item = {
            "key": k,
            "label": entry.get("label", k.replace("_", " ").title()),
            "url": entry.get("url", f"/api/html/{k}"),
            "icon": entry.get("icon", "default-icon"),
            "default": bool(entry.get("default", False)),
        }
        if item["default"]:
            defaults.append(item)
        items.append(item)

    if len(defaults) > 1:
        keys = ", ".join(d["key"] for d in defaults)
        raise RuntimeError(f"Multiple default nav items found in {path}: {keys}")

    return items

# lade nav_items beim App-Start
nav_items = load_nav()

# bestimme default item
default_item = next((it for it in nav_items if it.get("default")), None)
if default_item is None:
    if nav_items:
        default_item = nav_items[0]
    else:
        raise RuntimeError("nav_items is empty; navigation requires at least one entry")

@flask_app.context_processor
def inject_nav():
    return {"nav_items": nav_items, "user": "ottoadm"}

def make_page(resource_key, initial_url, list_partial=None, title=None, loader_fn=None):
    # Konventionen: list_partial aus Modul, title = label (falls nicht übergeben)
    if list_partial is None:
        list_partial = f"partials/lists/{resource_key}.html"
    if title is None:
        # finde label aus nav_items falls vorhanden
        label = next((it["label"] for it in nav_items if it["key"] == resource_key), None)
        title = label or resource_key.replace("_", " ").title()

    def page():
        context = {
            "active_tab": resource_key,
            "initial_content_url": initial_url,
            "title": title,
            "endpoint": initial_url,
            "container_id": f"tab-{resource_key}",
            "loading_id": f"{resource_key}-loading",
            "list_partial": list_partial,
        }
        if loader_fn:
            data = loader_fn()
            if not isinstance(data, dict):
                raise RuntimeError("loader_fn must return a dict")
            context.update(data)
        return render_template("index.html", **context)
    page.__name__ = f"page_{resource_key}"
    return page

# optional: mappe loader functions pro key (falls du serverseitig Daten liefern willst)
loader_map = {
    # "borg": load_borg_cfg,
    # "proxmox_jobs": load_proxmox_jobs,
}

# Root route verwendet default_item
@flask_app.route("/")
def index():
    return render_template("index.html",
                           active_tab=default_item["key"],
                           initial_content_url=default_item["url"])

# Routen programmatisch anlegen (nutzt Konventionen)
for item in nav_items:
    key = item["key"]
    url = item["url"]
    flask_app.add_url_rule(
        f"/{key}",
        endpoint=f"page_{key}",
        view_func=make_page(key, url, list_partial=None, title=None, loader_fn=loader_map.get(key))
    )

@flask_app.route("/confirm/<module>/<item>/<action>")
def confirm_action(module, item, action):

    container_id = request.args.get("container_id")
    loading_id = request.args.get("loading_id")
    enabled = request.args.get("enabled")  # kommt als "true"/"false" oder "1"/"0"
    description = request.args.get("description")

    # enabled in echtes Bool umwandeln
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("1", "true", "yes")

    # Aktivieren oder deaktivieren?
    if action == "toggle":
        verb = "deaktivieren" if enabled else "aktivieren"
        method = "post"
        confirm_url = f"/api/config/{module}/{item}/toggle"

    elif action == "delete":
        verb = "löschen"
        method = "delete"
        confirm_url = f"/api/config/{module}/{item}"

    return render_template(
        "partials/confirm_modal.html",
        description=description,
        verb=verb,
        confirm_url=confirm_url,
        method=method,
        container_id=container_id,
        loading_id=loading_id
    )


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
    from api.routers import html as tabs_router
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
