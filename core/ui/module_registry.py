"""
core/ui/module_registry.py  –  AstrapiFlaskUi V3  Modul-Registry

Navigation:
  1. app/templates/navigation/items.yaml   – optionaler Override (Reihenfolge, Label, Gruppe)
  2. core/templates/navigation/items.yaml  – Core-Module (sysinfo, settings)
  3. Alle geladenen App-Module die in keiner YAML stehen → automatisch angehängt

Ein neues Modul erscheint also automatisch in der Nav, sobald sein Ordner
existiert und eine Module-Instanz exportiert. Die YAML ist optional.
"""

from __future__ import annotations

import importlib.util
import sys
import warnings
from pathlib import Path

CORE_ROOT    = Path(__file__).resolve().parent           # core/ui/  (templates, static)
CORE_MOD_DIR = Path(__file__).resolve().parents[1] / "modules"  # core/modules/


class ModuleRegistry:
    """Kapselt das Modul-Verzeichnis der geladenen Module.

    Kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._registry: dict = {}

    def reset(self) -> None:
        """Setzt die Registry zurück (für Test-Isolation)."""
        self._registry = {}

    def update(self, modules: dict) -> None:
        """Aktualisiert die Registry mit einem Dict aus {key: module}."""
        self._registry.update(modules)

    def get(self, key: str):
        """Gibt eine Modul-Instanz anhand ihres Keys zurück oder None."""
        return self._registry.get(key)

    def all(self) -> dict:
        """Gibt eine Kopie der gesamten Registry zurück."""
        return dict(self._registry)

    def __contains__(self, key: str) -> bool:
        return key in self._registry

    def __getitem__(self, key: str):
        return self._registry[key]


# Modul-level Singleton – wird von load_modules() befüllt; von FastAPI-Templates genutzt
_mod_registry_instance = ModuleRegistry()

# Rückwärtskompatibilität: Code der direkt auf _mod_registry zugreift
# benutzt weiterhin das interne dict via diesen Alias
_mod_registry: dict = _mod_registry_instance._registry


# ── Laden ─────────────────────────────────────────────────────────────────────

def _load_from_dir(modules_dir: Path, pkg_prefix: str) -> dict:
    """Lädt alle Module-Instanzen aus einem Verzeichnis → {key: instance}."""
    from core.ui._base import Module

    found: dict[str, Module] = {}
    if not modules_dir.exists():
        return found

    for entry in sorted(modules_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        init_file = entry / "__init__.py"
        if not init_file.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"{pkg_prefix}.{entry.name}", init_file
            )
            mod = importlib.util.module_from_spec(spec)
            pkg_name = f"{pkg_prefix}.{entry.name}"
            sys.modules[pkg_name] = mod
            spec.loader.exec_module(mod)
            instance = getattr(mod, "module", None)
            if instance is None or not isinstance(instance, Module):
                warnings.warn(f"Modul '{entry.name}' ({pkg_prefix}): keine Module-Instanz gefunden")
                continue
            # module_root nur setzen wenn dieses Verzeichnis Templates hat
            # oder noch kein module_root gesetzt ist (z.B. app re-exportiert Core-Instanz)
            if instance.module_root is None or (entry / "templates").exists():
                instance.module_root = entry
            # settings.yaml nachladen wenn das Modul es nicht selbst gesetzt hat
            if not instance.settings_schema:
                settings_yaml = entry / "settings.yaml"
                if settings_yaml.exists():
                    import yaml as _yaml
                    with open(settings_yaml, encoding="utf-8") as _f:
                        instance.settings_schema = _yaml.safe_load(_f) or []
            found[instance.key] = instance
        except Exception as e:
            warnings.warn(f"Modul '{entry.name}' ({pkg_prefix}) konnte nicht geladen werden: {e}")

    return found


def load_modules(app_root: Path) -> list:
    """Lädt Module aus core/modules/, app/overrides/ und app/modules/.

    Priorität (höher überschreibt niedrigere):
      app/modules/    > app/overrides/ > core/modules/
    app/overrides/   – Module die Core-Module überschreiben/ergänzen
    app/modules/      – reine App-Module
    Reihenfolge im Ergebnis: core zuerst, dann app-exklusive.
    """
    core_mods = _load_from_dir(CORE_MOD_DIR,              "core.modules")
    ext_mods  = _load_from_dir(app_root / "overrides",   "app.overrides")
    app_mods  = _load_from_dir(app_root / "modules",      "app.modules")

    # module_root erben: Overrides ohne eigene Templates übernehmen Core-Pfad
    def _inherit_root(overrides: dict, base: dict) -> None:
        for key, m in overrides.items():
            if key in base:
                ref = base[key]
                if m.module_root is None or not (m.module_root / "templates").exists():
                    m.module_root = ref.module_root

    _inherit_root(ext_mods, core_mods)
    _inherit_root(app_mods, {**core_mods, **ext_mods})

    merged  = {**core_mods, **ext_mods, **app_mods}
    ordered = []
    seen: set = set()
    for key in sorted(core_mods):
        ordered.append(merged[key]); seen.add(key)
    for key in sorted({**ext_mods, **app_mods}):
        if key not in seen:
            ordered.append(merged[key]); seen.add(key)
    _mod_registry_instance.update({m.key: m for m in ordered})
    return ordered


# ── Registrieren ──────────────────────────────────────────────────────────────

def register_flask_modules(flask_app, modules: list, jinja_loaders: list) -> None:
    from jinja2 import FileSystemLoader, PrefixLoader

    for mod in modules:
        if mod.module_root:
            tpl_dir = mod.module_root / "templates"
            if tpl_dir.exists():
                # PrefixLoader mit mod.key als Prefix → unabhängig vom Ordnernamen.
                # render_template("hosts/partials/list.html") sucht in
                # {module_root}/templates/partials/list.html – egal ob der Ordner
                # "hosts", "test" oder anders heißt.
                jinja_loaders.insert(0, PrefixLoader(
                    {mod.key: FileSystemLoader(str(tpl_dir))}
                ))

        if mod.ui_blueprint is not None:
            try:
                flask_app.register_blueprint(mod.ui_blueprint)
            except Exception as e:
                warnings.warn(f"Blueprint '{mod.key}' konnte nicht registriert werden: {e}")


def register_fastapi_modules(fastapi_app, modules: list) -> None:
    for mod in modules:
        if mod.api_router is not None:
            try:
                fastapi_app.include_router(
                    mod.api_router,
                    prefix=f"/api/{mod.key}",
                    tags=[mod.key],
                )
            except Exception as e:
                warnings.warn(f"Router '{mod.key}' konnte nicht registriert werden: {e}")


# ── Navigation ────────────────────────────────────────────────────────────────

def build_nav_items(modules: list, app_root: Path) -> list[dict]:
    """Baut die nav_items-Liste ausschließlich aus app/config.yaml → navigation:.

    Nur was dort eingetragen ist, erscheint in der Navigation.
    label / icon kommen aus der modul.yaml des Moduls und können in der
    config.yaml überschrieben werden.
    Unbekannte Keys (kein geladenes Modul) werden mit einer Warnung übersprungen.
    """
    import yaml

    mod_map = {m.key: m for m in modules}

    config_yaml = app_root / "config.yaml"
    if not config_yaml.exists():
        warnings.warn("app/config.yaml nicht gefunden – Navigation ist leer.")
        return []

    with open(config_yaml, encoding="utf-8") as f:
        nav_raw: list[dict] = (yaml.safe_load(f) or {}).get("navigation", [])

    items: list[dict] = []
    current_group: str = ""

    for entry in nav_raw:
        key = entry.get("key")
        if not key:
            continue
        mod = mod_map.get(key)
        if mod is None:
            warnings.warn(f"Navigation: Eintrag '{key}' hat kein geladenes Modul – wird übersprungen.")
            continue
        group = entry.get("group") or mod.nav_group or ""
        if group != current_group:
            items.append({"separator": True, "group": group})
            current_group = group
        items.append({
            "key":     key,
            "label":   entry.get("label") or mod.label,
            "url":     mod.nav_url,
            "icon":    entry.get("icon")  or mod.icon,
            "default": bool(entry.get("default", False)),
        })

    _set_default(items)
    return items


def _set_default(items: list[dict]) -> None:
    """Setzt das erste Non-Separator-Item als Default wenn keines gesetzt ist."""
    if not any(not i.get("separator") and i.get("default") for i in items):
        for item in items:
            if not item.get("separator"):
                item["default"] = True
                break
