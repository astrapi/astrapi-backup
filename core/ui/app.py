"""
core/ui/app.py  –  AstrapiFlaskUi V3  Framework-Factory

Neu gegenüber V2:
  - Lädt alle Module aus app/modules/ automatisch
  - Registriert Modul-Flask-Blueprints und Template-Loader
  - Baut Navigation aus Modulen + optionaler items.yaml zusammen
  - Initialisiert Einstellungs-Registry (global + Modul-Defaults)
  - Registriert /settings als festen Endpunkt mit Speicher-Routen
"""

from __future__ import annotations

from flask import Flask, redirect, send_from_directory, render_template, request
from pathlib import Path
from jinja2 import ChoiceLoader, FileSystemLoader
import importlib.util
from typing import Optional, Callable

from .page_factory import register_pages
from .swagger_utils import register_ui_docs
from .module_registry import load_modules, register_flask_modules, build_nav_items
from .settings_registry import (
    init as settings_init, seed_defaults, set_many, all_settings,
)
from .storage import init as storage_init

CORE_ROOT = Path(__file__).resolve().parent


def _load_module_file(name: str, path: Path):
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def create(
    app_root:   Path,
    config:     Optional[dict] = None,
    extra_init: Optional[Callable] = None,
) -> Flask:
    """Erstellt und konfiguriert die Flask-Anwendung mit Modul-Unterstützung."""

    core_static = CORE_ROOT / "static"
    app_static  = app_root / "static"

    # ── Flask-Subklasse: app/static/ überschreibt core/static/ ──────────────
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

    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    if config:
        app.config.update(config)

    # ── App-Konfiguration laden ───────────────────────────────────────────────
    app_cfg: dict = {}
    cfg_yaml = app_root / "config.yaml"
    if cfg_yaml.exists():
        import yaml as _yaml
        with open(cfg_yaml, encoding="utf-8") as _f:
            _raw = _yaml.safe_load(_f) or {}
        _app = _raw.get("app", {})
        app_cfg = {
            "APP_NAME":    _app.get("name",       "myapp"),
            "APP_VERSION": _app.get("version",    "0.1.0"),
            "APP_LANG":    _app.get("lang",        "de"),
            "LIGHT_MODE":  bool(_app.get("light_mode", False)),
            "APP_LOGO_SVG": _app.get("logo_svg",  None),
        }
    else:
        for cfg_name in ("settings.py", "config.py"):
            cfg_path = app_root / cfg_name
            if cfg_path.exists():
                mod     = _load_module_file("app_settings", cfg_path)
                app_cfg = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
                break

    light_mode: bool = app_cfg.get("LIGHT_MODE", False)

    # ── Module laden ──────────────────────────────────────────────────────────
    modules = load_modules(app_root)

    # ── Einstellungs-Registry initialisieren ──────────────────────────────────
    settings_init(app_root)
    storage_init(app_root)
    global_defaults = {
        k: v for k, v in app_cfg.items()
        if k not in ("LIGHT_MODE", "APP_LOGO_SVG") and not callable(v)
    }
    seed_defaults(global_defaults, modules)

    # ── Template-Loader: Modul > App > Core ──────────────────────────────────
    app_templates  = app_root / "templates"
    core_templates = CORE_ROOT / "templates"

    base_loaders: list = []
    if app_templates.exists():
        base_loaders.append(FileSystemLoader(str(app_templates)))
    base_loaders.append(FileSystemLoader(str(core_templates)))

    # register_flask_modules fügt Modul-Loader vorne ein (höchste Priorität)
    all_loaders = list(base_loaders)
    register_flask_modules(app, modules, all_loaders)

    app.jinja_env.loader = ChoiceLoader(all_loaders)

    # ── Globale Template-Variablen ────────────────────────────────────────────
    @app.context_processor
    def _inject_globals():
        return {
            "app_name":     app_cfg.get("APP_NAME",     "myapp"),
            "app_version":  app_cfg.get("APP_VERSION",  "0.1.0"),
            "app_logo_svg": app_cfg.get("APP_LOGO_SVG", None),
            "app_lang":     app_cfg.get("APP_LANG",     "de"),
            "light_mode":   light_mode,
            "modules":      modules,
        }

    # ── Navigation aus Modulen + optionaler items.yaml ────────────────────────
    nav_items  = build_nav_items(modules, app_root=app_root)

    @app.context_processor
    def _inject_nav():
        return {"nav_items": nav_items}

    # ── Seiten-Routen registrieren (Page + Tab + List pro Nav-Item) ───────────
    # "settings" wird von _register_settings_routes separat behandelt
    # Modul-Keys mit eigenem Blueprint registrieren tab/list selbst
    module_keys = {m.key for m in modules if m.ui_blueprint is not None}
    # Nur "settings" herausfiltern — Modul-Keys bleiben drin für Shell+Redirect
    register_pages(app, [it for it in nav_items if it.get("key") != "settings"],
                   shell_only_keys=module_keys)

    # ── Optionale App-Blueprints: app/routes/__init__.py ─────────────────────
    routes_init_path = app_root / "routes" / "__init__.py"
    if routes_init_path.exists():
        mod = _load_module_file("app_routes", routes_init_path)
        if hasattr(mod, "register"):
            mod.register(app)
        elif hasattr(mod, "blueprint"):
            app.register_blueprint(mod.blueprint)

    # ── Einstellungs-Routen ───────────────────────────────────────────────────
    # Hat ein settings-Modul einen eigenen Blueprint, übernimmt er /ui/settings/content.
    settings_has_blueprint = any(m.key == "settings" and m.ui_blueprint for m in modules)
    _register_settings_routes(app, modules, app_cfg,
                               skip_content=settings_has_blueprint)

    # ── Projektspezifischer Hook ──────────────────────────────────────────────
    if extra_init:
        extra_init(app)

    # ── Root-Redirect → erstes/default Nav-Item ───────────────────────────────
    default_item = next(
        (it for it in nav_items if not it.get("separator") and it.get("default")),
        next((it for it in nav_items if not it.get("separator")), None),
    )
    if default_item:
        @app.get("/")
        def _root():
            return redirect(f"/{default_item['key']}")

    # ── Swagger UI-Docs ───────────────────────────────────────────────────────
    swagger_html = CORE_ROOT / "static" / "swagger.html"
    if not swagger_html.exists():
        swagger_html = app_root / "static" / "swagger.html"
    try:
        register_ui_docs(app, project_root=CORE_ROOT.parent, swagger_html_path=swagger_html)
    except Exception as e:
        import warnings
        warnings.warn(f"UI-Docs konnten nicht registriert werden: {e}")

    return app


# ─────────────────────────────────────────────────────────────────────────────
# Einstellungs-Routen
# ─────────────────────────────────────────────────────────────────────────────

def _register_settings_routes(app: Flask, modules: list, app_cfg: dict,
                               skip_content: bool = False) -> None:
    """Registriert Tab- und Speicher-Routen für die Einstellungsseite.

    skip_content: True wenn ein settings-Modul mit Blueprint /ui/settings/content selbst bedient.
    """

    def _ctx(flash: str = "") -> dict:
        return {
            "settings":      all_settings(),
            "modules":       modules,
            "app_cfg":       app_cfg,
            "flash_message": flash,
        }

    @app.route("/settings")
    def settings_shell():
        return render_template(
            "index.html",
            active_tab="settings",
            initial_content_url="/ui/settings/content",
            title="Einstellungen",
        )

    if not skip_content:
        @app.route("/ui/settings/content")
        def settings_content():
            return render_template("partials/lists/settings.html", **_ctx())

    @app.route("/ui/settings/save/global", methods=["POST"])
    def settings_save_global():
        set_many(request.form.to_dict())
        return render_template(
            "partials/lists/settings.html",
            **_ctx("Globale Einstellungen gespeichert."),
        )

    @app.route("/ui/settings/save/module/<module_key>", methods=["POST"])
    def settings_save_module(module_key: str):
        mod = next((m for m in modules if m.key == module_key), None)
        if mod is None:
            return "Modul nicht gefunden", 404
        prefixed = {f"module.{module_key}.{k}": v
                    for k, v in request.form.to_dict().items()}
        set_many(prefixed)
        return render_template(
            "partials/lists/settings.html",
            **_ctx(f"Einstellungen für \"{mod.label}\" gespeichert."),
        )
