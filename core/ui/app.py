from flask import Flask, redirect, send_from_directory
from pathlib import Path
from jinja2 import ChoiceLoader, FileSystemLoader

from .navigation import load_nav
from .page_factory import register_pages

CORE_ROOT = Path(__file__).resolve().parents[1]


def create(app_root: Path, config: dict | None = None, extra_init=None) -> Flask:
    """Erstellt die Flask-App.

    Args:
        app_root:  Pfad zum app/-Verzeichnis des Projekts.
        config:    Optionales Dict mit Flask-Config-Werten.

    Template-Auflösung (Priorität: app > core):
      Zuerst wird in app/templates/ gesucht, dann in core/templates/.

    Static-Dateien:
      core/static/ ist das primäre static_folder – url_for('static', ...)
      funktioniert damit normal. app/static/ hat Vorrang via
      send_static_file()-Override, ohne den Endpunkt neu zu registrieren.
    """
    core_static = CORE_ROOT / "static"
    app_static  = app_root / "static"

    # ── Flask-Subklasse: app/static/ hat Vorrang, core/static/ ist Fallback ──
    class _App(Flask):
        def send_static_file(self, filename: str):
            candidate = app_static / filename
            if app_static.exists() and candidate.is_file():
                return send_from_directory(str(app_static), filename)
            return super().send_static_file(filename)

    app = _App(
        __name__,
        static_folder=str(core_static),
        static_url_path="/static",
    )

    # ── Config ────────────────────────────────────────────────────────────────
    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    if config:
        app.config.update(config)

    # ── Templates: app überschreibt core ─────────────────────────────────────
    app_templates  = app_root / "templates"
    core_templates = CORE_ROOT / "templates"

    loaders = []
    if app_templates.exists():
        loaders.append(FileSystemLoader(str(app_templates)))
    loaders.append(FileSystemLoader(str(core_templates)))

    app.jinja_env.loader = ChoiceLoader(loaders)

    # ── App-Config importieren ────────────────────────────────────────────────
    app_config_path = app_root / "settings.py"
    app_cfg: dict = {}
    if app_config_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("app_config", app_config_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        app_cfg = {k: v for k, v in vars(mod).items() if not k.startswith("_")}

    # ── Light-Mode ────────────────────────────────────────────────────────────
    light_mode: bool = app_cfg.get("LIGHT_MODE", False)

    # ── Context Processor ─────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        return {
            "app_name":     app_cfg.get("APP_NAME",    "myapp"),
            "app_version":  app_cfg.get("APP_VERSION", "0.1.0"),
            "app_logo_svg": app_cfg.get("APP_LOGO_SVG", None),
            "app_lang":     app_cfg.get("APP_LANG",    "de"),
            "light_mode":   light_mode,
        }

    # ── Navigation ────────────────────────────────────────────────────────────
    # Im Light-Mode: items.light.yaml (nur Repos/Browser/Stats)
    nav_name = "items.light.yaml" if light_mode else "items.yaml"
    nav_yaml = app_root / "templates" / "navigation" / nav_name
    if not nav_yaml.exists():
        raise FileNotFoundError(f"Nav-Config nicht gefunden: {nav_yaml}")

    nav_items = load_nav(nav_yaml)

    @app.context_processor
    def inject_nav():
        return {"nav_items": nav_items}

    # ── Routen ────────────────────────────────────────────────────────────────
    register_pages(app, nav_items)

    # ── App-spezifische Erweiterungen ────────────────────────────────────────
    if extra_init:
        extra_init(app)

    default_item = next((it for it in nav_items if not it.get("separator") and it.get("default")), 
                        next(it for it in nav_items if not it.get("separator")))

    @app.get("/")
    def root():
        return redirect(f"/{default_item['key']}")

    return app
