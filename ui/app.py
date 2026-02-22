from flask import Flask, render_template
from pathlib import Path
from .navigation import load_nav
from .context_processors import inject_common, inject_nav
from .modal_routes import register_modal_routes
from .page_factory import register_pages

from apispec import APISpec

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"


def add_ui_routes_to_spec(app):
    with app.test_request_context():
        for rule in app.url_map.iter_rules():

            if rule.rule in ("/ui/docs", "/ui/openapi.json", "/static/<path:filename>"):
                continue

            methods = [m.lower() for m in rule.methods if m in ("GET", "POST", "DELETE")]
            if not methods:
                continue

            view = app.view_functions.get(rule.endpoint)

            # -----------------------------------------
            # TAG aus Decorator lesen
            # -----------------------------------------
            tag = getattr(view, "_ui_tag", "default")  # Default-Tag: "UI"

            # -----------------------------------------
            # Source-File ermitteln
            # -----------------------------------------
            source_file = None
            if view and hasattr(view, "__code__"):
                source_file = view.__code__.co_filename

            relative_path = None
            if source_file:
                try:
                    relative_path = str(Path(source_file).resolve().relative_to(ROOT))
                except ValueError:
                    relative_path = source_file

            # -----------------------------------------
            # Operations erzeugen
            # -----------------------------------------
            operations = {
                method: {
                    "summary": f"{method.upper()} {rule.rule}",
                    "description": f"Defined in: {relative_path}" if relative_path else "",
                    "tags": [tag],   # ← HIER wird dein Tag gesetzt
                    "responses": {"200": {"description": "HTML response"}},
                }
                for method in methods
            }

            # Path-Parameter
            params = [
                {
                    "in": "path",
                    "name": arg,
                    "required": True,
                    "schema": {"type": "string"},
                }
                for arg in rule.arguments
            ]

            if params:
                for op in operations.values():
                    op["parameters"] = params

            app.apispec._paths[rule.rule] = operations




def create():
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
    )

    # KEIN FlaskPlugin
    app.apispec = APISpec(
        title="backupctl ui-routen",
        version="1.0.0",
        openapi_version="3.0.2",
        info={"description": "Dokumentation der UI-Routen"},
    )

    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )

    nav_items = load_nav()
    app.context_processor(inject_common)
    app.context_processor(lambda: inject_nav(nav_items))

    register_pages(app, nav_items)
    register_modal_routes(app)

    @app.route("/ui/docs")
    def ui_docs():
        html = open("static/swagger.html").read()
        html = html.replace("{{OPENAPI_URL}}", "/ui/openapi.json")
        return html


    @app.route("/ui/openapi.json")
    def openapi_json():
        return app.apispec.to_dict()

    # Nur diese eine Zeile für die Doku:
    add_ui_routes_to_spec(app)

    return app
