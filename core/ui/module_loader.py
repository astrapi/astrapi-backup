"""
core/ui/module_loader.py  –  Lädt modul.yaml und erstellt Module-Instanz

modul.yaml liegt im Root jedes Moduls neben __init__.py:

  label:       Hosts
  icon:        server
  nav_group:   Module
  nav_default: true

  settings_defaults:
    default_port: "22"
"""

import yaml
from pathlib import Path


def load_modul(module_dir: Path, key: str, api_router, ui_blueprint) -> "Module":
    from core.ui._base import Module

    yaml_path = module_dir / "modul.yaml"
    cfg = {}
    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # settings_template automatisch setzen wenn Datei vorhanden
    settings_yaml = module_dir / "settings.yaml"
    settings_schema: list = []
    if settings_yaml.exists():
        with open(settings_yaml, encoding="utf-8") as f:
            settings_schema = yaml.safe_load(f) or []

    # Defaults aus settings.yaml extrahieren; modul.yaml settings_defaults haben Vorrang
    schema_defaults = {
        field["key"]: field["default"]
        for field in settings_schema
        if "key" in field and "default" in field
    }
    merged_defaults = {**schema_defaults, **cfg.get("settings_defaults", {})}

    return Module(
        key               = key,
        label             = cfg.get("label",       key.capitalize()),
        icon              = cfg.get("icon",         "list"),
        api_router        = api_router,
        ui_blueprint      = ui_blueprint,
        nav_group         = cfg.get("nav_group",    "Module"),
        nav_default       = bool(cfg.get("nav_default", False)),
        settings_defaults = merged_defaults,
        settings_schema   = settings_schema,
        card_actions      = cfg.get("card_actions", []),
    )
