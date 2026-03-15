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

import threading
from pathlib import Path
from typing import Any
import yaml


class _SafeLoader(yaml.SafeLoader):
    """SafeLoader der Python-spezifische Tags (!!python/…) ignoriert statt abzubrechen."""


_SafeLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/",
    lambda loader, suffix, node: None,
)


class SettingsRegistry:
    """Kapselt den gesamten Zustand der Einstellungs-Registry.

    Alle öffentlichen Methoden sind thread-safe.
    Die Klasse kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._settings_file: Path | None = None
        self._cache: dict = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Setzt den internen Zustand zurück (für Test-Isolation)."""
        with self._lock:
            self._settings_file = None
            self._cache = {}

    def init(self, app_root: Path) -> None:
        """Initialisiert die Registry mit dem Pfad zu settings.yaml."""
        data_dir = app_root / "data"
        data_dir.mkdir(exist_ok=True)
        self._settings_file = data_dir / "settings.yaml"
        with self._lock:
            self._cache = self._load()

    def _load(self) -> dict:
        """Liest settings.yaml – muss unter _lock aufgerufen werden."""
        if self._settings_file and self._settings_file.exists():
            with open(self._settings_file, encoding="utf-8") as f:
                return yaml.load(f, Loader=_SafeLoader) or {}
        return {}

    def _save(self) -> None:
        """Schreibt _cache auf Disk – muss unter _lock aufgerufen werden."""
        if self._settings_file:
            with open(self._settings_file, "w", encoding="utf-8") as f:
                yaml.dump(self._cache, f, allow_unicode=True, default_flow_style=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Liest einen globalen Einstellungswert."""
        with self._lock:
            return self._cache.get(key, default)

    def get_module(self, module_key: str, key: str, default: Any = None) -> Any:
        """Liest einen Modul-Einstellungswert."""
        with self._lock:
            return self._cache.get(f"module.{module_key}.{key}", default)

    def set(self, key: str, value: Any) -> None:
        """Setzt einen globalen Einstellungswert und speichert."""
        with self._lock:
            self._cache[key] = value
            self._save()

    def set_module(self, module_key: str, key: str, value: Any) -> None:
        """Setzt einen Modul-Einstellungswert und speichert."""
        with self._lock:
            self._cache[f"module.{module_key}.{key}"] = value
            self._save()

    def set_many(self, values: dict) -> None:
        """Setzt mehrere Werte auf einmal und speichert einmalig."""
        with self._lock:
            self._cache.update(values)
            self._save()

    def all_settings(self) -> dict:
        """Gibt eine Kopie aller gespeicherten Einstellungen zurück."""
        with self._lock:
            return dict(self._cache)

    def seed_defaults(self, global_defaults: dict, modules: list) -> None:
        """Füllt fehlende Werte mit Defaults auf und bereinigt verwaiste Modul-Keys.

        Beim Start einmalig aufrufen. Entfernt alle module.X.*-Keys für Module,
        die nicht mehr in ``modules`` vorhanden sind.
        """
        with self._lock:
            changed = False
            for k, v in global_defaults.items():
                if k not in self._cache:
                    self._cache[k] = v
                    changed = True
            for mod in modules:
                for k, v in mod.settings_defaults.items():
                    full_key = f"module.{mod.key}.{k}"
                    if full_key not in self._cache:
                        self._cache[full_key] = v
                        changed = True
            # Verwaiste Modul-Keys entfernen
            known = {mod.key for mod in modules}
            orphaned = [
                k for k in self._cache
                if k.startswith("module.") and k.split(".")[1] not in known
            ]
            for k in orphaned:
                del self._cache[k]
            if changed or orphaned:
                self._save()


# Modul-level Singleton
_registry = SettingsRegistry()


# ── Shims (halten alle bestehenden Aufrufstellen kompatibel) ───────────────────

def init(app_root: Path) -> None:
    """Initialisiert die Registry mit dem Pfad zu settings.yaml."""
    _registry.init(app_root)


def get(key: str, default: Any = None) -> Any:
    """Liest einen globalen Einstellungswert."""
    return _registry.get(key, default)


def get_module(module_key: str, key: str, default: Any = None) -> Any:
    """Liest einen Modul-Einstellungswert."""
    return _registry.get_module(module_key, key, default)


def set(key: str, value: Any) -> None:
    """Setzt einen globalen Einstellungswert und speichert."""
    _registry.set(key, value)


def set_module(module_key: str, key: str, value: Any) -> None:
    """Setzt einen Modul-Einstellungswert und speichert."""
    _registry.set_module(module_key, key, value)


def set_many(values: dict) -> None:
    """Setzt mehrere Werte auf einmal und speichert einmalig."""
    _registry.set_many(values)


def all_settings() -> dict:
    """Gibt eine Kopie aller gespeicherten Einstellungen zurück."""
    return _registry.all_settings()


def seed_defaults(global_defaults: dict, modules: list) -> None:
    """Füllt fehlende Werte mit Defaults auf (beim Start einmalig aufrufen)."""
    _registry.seed_defaults(global_defaults, modules)
