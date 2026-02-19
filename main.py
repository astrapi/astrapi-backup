# # main.py
# from pathlib import Path
# import os
# import yaml
# import logging

# from fastapi import FastAPI
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import RedirectResponse
# from starlette.middleware.wsgi import WSGIMiddleware
# import uvicorn

# from flask import Flask, render_template, send_from_directory, abort, url_for, request

# # -------------------------
# # Projektpfade
# # -------------------------
# ROOT = Path(__file__).resolve().parent
# TEMPLATES_DIR = ROOT / "templates"
# STATIC_DIR = ROOT / "static"
# CONFIG_DIR = ROOT / "config"
# NAV_YAML_PATH = os.path.join(os.path.dirname(__file__), "templates", "navigation", "items.yaml")

# # -------------------------
# # Hilfsfunktionen
# # -------------------------
# def load_yaml(path: Path):
#     if not path.exists():
#         return {}
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             return yaml.safe_load(f) or {}
#     except Exception:
#         logging.exception("Fehler beim Laden von YAML: %s", path)
#         return {}

# # -------------------------
# # Flask UI App (exportiert app)
# # -------------------------
# flask_app = Flask(
#     __name__,
#     template_folder=str(TEMPLATES_DIR),
#     static_folder=str(STATIC_DIR),
#     static_url_path="/static"
# )

# flask_app.config.update(
#     DEBUG=True,
#     TEMPLATES_AUTO_RELOAD=True,
#     SEND_FILE_MAX_AGE_DEFAULT=0
# )


# @flask_app.context_processor
# def inject_common():
#     # Globale Template-Variablen (kann erweitert werden)
#     return {"app_name": "backupctl"}

# def load_nav(path=NAV_YAML_PATH):
#     try:
#         with open(path, "r", encoding="utf-8") as f:
#             raw = yaml.safe_load(f) or []
#     except FileNotFoundError:
#         raise RuntimeError(f"Navigation file not found: {path}")
#     except yaml.YAMLError as e:
#         raise RuntimeError(f"Error parsing navigation YAML: {e}")

#     items = []
#     defaults = []
#     for entry in raw:
#         k = entry.get("key")
#         if not k:
#             continue
#         item = {
#             "key": k,
#             "label": entry.get("label", k.replace("_", " ").title()),
#             "url": entry.get("url", f"/api/html/{k}"),
#             "icon": entry.get("icon", "default-icon"),
#             "default": bool(entry.get("default", False)),
#         }
#         if item["default"]:
#             defaults.append(item)
#         items.append(item)

#     if len(defaults) > 1:
#         keys = ", ".join(d["key"] for d in defaults)
#         raise RuntimeError(f"Multiple default nav items found in {path}: {keys}")

#     return items

# # lade nav_items beim App-Start
# nav_items = load_nav()

# # bestimme default item
# default_item = next((it for it in nav_items if it.get("default")), None)
# if default_item is None:
#     if nav_items:
#         default_item = nav_items[0]
#     else:
#         raise RuntimeError("nav_items is empty; navigation requires at least one entry")

# @flask_app.context_processor
# def inject_nav():
#     return {"nav_items": nav_items, "user": "ottoadm"}

# def make_page(resource_key, initial_url, list_partial=None, title=None, loader_fn=None):
#     # Konventionen: list_partial aus Modul, title = label (falls nicht übergeben)
#     if list_partial is None:
#         list_partial = f"partials/lists/{resource_key}.html"
#     if title is None:
#         # finde label aus nav_items falls vorhanden
#         label = next((it["label"] for it in nav_items if it["key"] == resource_key), None)
#         title = label or resource_key.replace("_", " ").title()

#     def page():
#         context = {
#             "active_tab": resource_key,
#             "initial_content_url": initial_url,
#             "title": title,
#             "endpoint": initial_url,
#             "container_id": f"tab-{resource_key}",
#             "loading_id": f"{resource_key}-loading",
#             "list_partial": list_partial,
#         }
#         return render_template("index.html", **context)
#     page.__name__ = f"page_{resource_key}"
#     return page

# # Root route verwendet default_item
# @flask_app.route("/")
# def index():
#     return render_template("index.html",
#                            active_tab=default_item["key"],
#                            initial_content_url=default_item["url"])

# # Routen programmatisch anlegen (nutzt Konventionen)
# for item in nav_items:
#     key = item["key"]
#     url = item["url"]
#     flask_app.add_url_rule(
#         f"/{key}",
#         endpoint=f"page_{key}",
#         view_func=make_page(key, url, list_partial=None, title=None)
#     )

# @flask_app.route("/confirm/<module>/<item>/<action>")
# def confirm_action(module, item, action):

#     container_id = request.args.get("container_id")
#     loading_id = request.args.get("loading_id")
#     enabled = request.args.get("enabled")  # kommt als "true"/"false" oder "1"/"0"
#     description = request.args.get("description")

#     # enabled in echtes Bool umwandeln
#     if isinstance(enabled, str):
#         enabled = enabled.lower() in ("1", "true", "yes")

#     # Aktivieren oder deaktivieren?
#     if action == "toggle":
#         verb = "deaktivieren" if enabled else "aktivieren"
#         method = "post"
#         confirm_url = f"/api/config/{module}/{item}/toggle"

#     elif action == "delete":
#         verb = "löschen"
#         method = "delete"
#         confirm_url = f"/api/config/{module}/{item}"

#     return render_template(
#         "partials/confirm_modal.html",
#         description=description,
#         verb=verb,
#         confirm_url=confirm_url,
#         method=method,
#         container_id=container_id,
#         loading_id=loading_id
#     )


# def load_schema(module: str):
#     with open("templates/partials/create_edit/schemas.yaml", "r") as f:
#         data = yaml.safe_load(f)
#     return data[module]

# @flask_app.route("/modal/<module>/create")
# def open_create_modal(module):

#     container_id = request.args.get("container_id")
#     loading_id = request.args.get("loading_id")

#     schema = load_schema(module)

#     submit_url = f"/api/config/{module}/create?container_id={container_id}&loading_id={loading_id}"

#     return render_template(
#         "partials/create_edit/create_edit_modal.html",
#         schema=schema,
#         values=None,          # keine Werte beim Erstellen
#         item=None,            # wichtig für Titel
#         module=module,
#         submit_url=submit_url,
#         container_id=container_id,
#         loading_id=loading_id
#     )

# # Optional: favicon (falls nicht in /static automatisch)
# @flask_app.route("/favicon.ico")
# def favicon():
#     fav_dir = STATIC_DIR / "favicon"
#     if (fav_dir / "favicon-32x32.png").exists():
#         return send_from_directory(str(fav_dir), "favicon-32x32.png")
#     abort(404)

# # -------------------------
# # FastAPI App (API + Static mount + WSGI mount)
# # -------------------------
# # Setze docs- und openapi-URLs unter /api
# app = FastAPI(
#     title="backupctl API + UI",
#     docs_url="/api/docs",
#     redoc_url="/api/redoc",
#     openapi_url="/api/openapi.json"
# )

# # 1) StaticFiles mount muss VOR dem WSGI-Mount stehen
# app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# # 2) API-Router einbinden (muss VOR dem WSGI-Mount passieren)
# try:
#     from api.routers import html as tabs_router
#     from api.routers.config import config_router

#     app.include_router(tabs_router.router)  # bindet /api/tabs/*

#     resources = [ "borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync", ]
#     for name in resources: 
#         router = config_router(name, tag=name) 
#         app.include_router(router, prefix=f"/api/config/{name}")

# except Exception:
#     logging.exception("API-Router konnten nicht eingebunden werden. Prüfe api/routers/*")

# # 3) /api root: Redirect auf /api/docs (oder gib Info zurück)
# @app.get("/api")
# def api_root():
#     # Redirect zur Swagger UI
#     return RedirectResponse(url="/api/docs")

# # 4) Kleiner health endpoint unter /api
# @app.get("/api/health")
# def health():
#     return {"status": "ok"}

# # 5) Mount Flask UI unter Root (als letztes)
# app.mount("/", WSGIMiddleware(flask_app))

# # -------------------------
# # CLI / Debug Start
# # -------------------------
# if __name__ == "__main__":
#     # Für Entwicklung: uvicorn startet die kombinierte App
#     uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=True)

#main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware
from ui.flask_app import create_flask_app
from api.api_app import create_api_app
import uvicorn

def create_app():
    api = create_api_app()
    ui = create_flask_app()

    app = FastAPI()

    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    app.mount("/api", api)
    app.mount("/", WSGIMiddleware(ui))

    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9999, reload=True)


