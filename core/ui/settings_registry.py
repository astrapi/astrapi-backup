"""
core/ui/settings_registry.py  –  Einstellungs-Registry

Verwaltet globale App-Einstellungen und Modul-Einstellungen.
Persistenz in app/data/settings.yaml.

Globale Einstellungen kommen aus app/settings.py (Defaults)
und werden in app/data/settings.yaml gespeichert.

Modul-Einstellungen kommen aus module.settings_defaults
und werden in app/data/settings.yaml unter dem Modul-Key gespeichert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


class _SafeLoader(yaml.SafeLoader):
    """SafeLoader der Python-spezifische Tags (!!python/…) ignoriert statt abzubrechen."""


_SafeLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/",
    lambda loader, suffix, node: None,
)


_SETTINGS_FILE: Path | None = None
_cache: dict = {}


def init(app_root: Path) -> None:
    """Initialisiert die Registry mit dem Pfad zu settings.yaml."""
    global _SETTINGS_FILE, _cache
    data_dir = app_root / "data"
    data_dir.mkdir(exist_ok=True)
    _SETTINGS_FILE = data_dir / "settings.yaml"
    _cache = _load()


def _load() -> dict:
    if _SETTINGS_FILE and _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            return yaml.load(f, Loader=_SafeLoader) or {}
    return {}


def _save() -> None:
    if _SETTINGS_FILE:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(_cache, f, allow_unicode=True, default_flow_style=False)


def get(key: str, default: Any = None) -> Any:
    """Liest einen globalen Einstellungswert."""
    return _cache.get(key, default)


def get_module(module_key: str, key: str, default: Any = None) -> Any:
    """Liest einen Modul-Einstellungswert."""
    return _cache.get(f"module.{module_key}.{key}", default)


def set(key: str, value: Any) -> None:
    """Setzt einen globalen Einstellungswert und speichert."""
    _cache[key] = value
    _save()


def set_module(module_key: str, key: str, value: Any) -> None:
    """Setzt einen Modul-Einstellungswert und speichert."""
    _cache[f"module.{module_key}.{key}"] = value
    _save()


def set_many(values: dict) -> None:
    """Setzt mehrere Werte auf einmal und speichert einmalig."""
    _cache.update(values)
    _save()


def all_settings() -> dict:
    """Gibt alle gespeicherten Einstellungen zurück."""
    return dict(_cache)


def seed_defaults(global_defaults: dict, modules: list) -> None:
    """Füllt fehlende Werte mit Defaults auf (beim Start einmalig aufrufen)."""
    changed = False
    for k, v in global_defaults.items():
        if k not in _cache:
            _cache[k] = v
            changed = True
    for mod in modules:
        for k, v in mod.settings_defaults.items():
            full_key = f"module.{mod.key}.{k}"
            if full_key not in _cache:
                _cache[full_key] = v
                changed = True
    if changed:
        _save()
