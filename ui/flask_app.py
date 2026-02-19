# ui/flask_app.py
from flask import Flask
from pathlib import Path
from .navigation import load_nav
from .context_processors import inject_common, inject_nav
from .modal_routes import register_modal_routes
from .page_factory import register_pages

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

def create_flask_app():
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static"
    )

    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0
    )

    # Navigation laden
    nav_items = load_nav()

    # Context processors
    app.context_processor(inject_common)
    app.context_processor(lambda: inject_nav(nav_items))

    # Pages registrieren
    register_pages(app, nav_items)

    # Modal routes registrieren
    register_modal_routes(app)

    return app
