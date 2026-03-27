# api/templates.py – zentrale Jinja2-Instanz mit ChoiceLoader (app/ > module/ > core/)
from pathlib import Path
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader

from backupctl._paths import package_dir as _package_dir

_APP_ROOT      = _package_dir()
_APP_TEMPLATES = _APP_ROOT / "templates"

import astrapi.core.ui as _astrapi_core_ui
_CORE_TEMPLATES = Path(_astrapi_core_ui.__file__).resolve().parent / "templates"

# Basis-Loader: app/templates/ > core/ui/templates/
_base_loaders: list = [
    FileSystemLoader(str(_APP_TEMPLATES)),
    FileSystemLoader(str(_CORE_TEMPLATES)),
]

# PrefixLoader für jedes Modul das ein templates/-Unterverzeichnis hat
# → render_template("borg/partials/list.html") → modules/borg/templates/partials/list.html
_prefix_loaders: list = []
_CORE_MODULES = Path(_astrapi_core_ui.__file__).resolve().parents[1] / "modules"
for _search_root in (_APP_ROOT / "modules", _CORE_MODULES):
    if not _search_root.is_dir():
        continue
    for _mod_dir in sorted(_search_root.iterdir()):
        if not _mod_dir.is_dir() or _mod_dir.name.startswith("_"):
            continue
        _tpl_dir = _mod_dir / "templates"
        if _tpl_dir.is_dir():
            _prefix_loaders.append(
                PrefixLoader({_mod_dir.name: FileSystemLoader(str(_tpl_dir))})
            )

# Environment direkt bauen und per env= übergeben – vermeidet den Jinja2 3.1.5+
# Cache-Key-Bug bei dem globals (dict) unhashbar als LRU-Key verwendet wird.
_env = Environment(loader=ChoiceLoader(_prefix_loaders + _base_loaders), autoescape=True)
templates = Jinja2Templates(env=_env)

# Jinja2-Instanz für core-Module bereitstellen
from astrapi.core.ui.fastapi_templates import configure as _configure_fastapi_templates
_configure_fastapi_templates(templates)


# ── Template-Globals: Funktionen die list_wrapper.html braucht ────────────────
# (entsprechen den Flask-Context-Processor-Funktionen in core/ui/app.py)

def _module_label(key: str) -> str:
    from astrapi.core.ui.module_registry import _mod_registry
    m = _mod_registry.get(key)
    return m.label if m else key.replace("_", " ").title()


def _module_has_settings(key: str) -> bool:
    from astrapi.core.ui.module_registry import _mod_registry
    m = _mod_registry.get(key)
    return bool(m and m.settings_schema)


def _module_card_actions(key: str) -> list:
    from astrapi.core.ui.module_registry import _mod_registry
    m = _mod_registry.get(key)
    return m.card_actions if m else []


def _col_widths(module_key: str) -> str:
    from astrapi.core.ui.settings_registry import get as settings_get
    return settings_get(f"ui.col_widths.{module_key}", "{}")


def _resolve_remote_host(remote_id) -> str:
    if not remote_id:
        return "—"
    try:
        from backupctl.modules.remotes.engine import get_remote
        r = get_remote(remote_id)
        return r.get("host") or "—" if r else "—"
    except Exception:
        return "—"


def _last_run_status(module: str, item_id) -> str | None:
    try:
        from astrapi.core.system.activity_log import list_runs_for_item
        runs = list_runs_for_item(module, str(item_id), limit=5)
        for run in runs:
            if run.get("status") != "running":
                return run.get("status")
    except Exception:
        pass
    return None


_env.globals["module_label"]        = _module_label
_env.globals["module_has_settings"] = _module_has_settings
_env.globals["module_card_actions"] = _module_card_actions
_env.globals["col_widths"]          = _col_widths
_env.globals["resolve_remote_host"] = _resolve_remote_host
_env.globals["last_run_status"]     = _last_run_status
