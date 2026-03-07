"""
core/ui/module_loader.py  –  Lädt modul.yaml und erstellt AstrapiModule-Instanz

modul.yaml liegt im Root jedes Moduls neben __init__.py:

  label:       Hosts
  icon:        server
  nav_group:   Module
  nav_default: true

  settings_defaults:
    default_port: "22"

settings_template wird automatisch gesetzt wenn
templates/partials/settings_section.html existiert.
"""

import yaml
from pathlib import Path


def load_modul(module_dir: Path, key: str, api_router, ui_blueprint) -> "AstrapiModule":
    from app.modules._base import AstrapiModule

    yaml_path = module_dir / "modul.yaml"
    cfg = {}
    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # settings_template automatisch setzen wenn Datei vorhanden
    tpl = module_dir / "templates" / "partials" / "settings_section.html"
    settings_template = f"{key}/partials/settings_section.html" if tpl.exists() else None

    return AstrapiModule(
        key               = key,
        label             = cfg.get("label",       key.capitalize()),
        icon              = cfg.get("icon",         "list"),
        api_router        = api_router,
        ui_blueprint      = ui_blueprint,
        nav_group         = cfg.get("nav_group",    "Module"),
        nav_default       = bool(cfg.get("nav_default", False)),
        settings_template = settings_template,
        settings_defaults = cfg.get("settings_defaults", {}),
    )
