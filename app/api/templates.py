# api/templates.py – zentrale Jinja2-Instanz mit ChoiceLoader (app/ > module/ > core/)
from pathlib import Path
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

_APP_ROOT       = Path(__file__).resolve().parent.parent          # = app/
_PROJECT_ROOT   = _APP_ROOT.parent                                # = backupctl/
_APP_TEMPLATES  = _APP_ROOT      / "templates"
_CORE_TEMPLATES = _PROJECT_ROOT  / "core" / "ui" / "templates"

templates = Jinja2Templates(directory=str(_APP_TEMPLATES))

# Basis-Loader: app/templates/ > core/ui/templates/
_base_loaders: list = [
    FileSystemLoader(str(_APP_TEMPLATES)),
    FileSystemLoader(str(_CORE_TEMPLATES)),
]

# PrefixLoader für jedes Modul das ein templates/-Unterverzeichnis hat
# → render_template("borg/partials/list.html") → modules/borg/templates/partials/list.html
_prefix_loaders: list = []
_modules_dir = _APP_ROOT / "modules"
if _modules_dir.is_dir():
    for _mod_dir in sorted(_modules_dir.iterdir()):
        if not _mod_dir.is_dir() or _mod_dir.name.startswith("_"):
            continue
        _tpl_dir = _mod_dir / "templates"
        if _tpl_dir.is_dir():
            _prefix_loaders.append(
                PrefixLoader({_mod_dir.name: FileSystemLoader(str(_tpl_dir))})
            )

templates.env.loader = ChoiceLoader(_prefix_loaders + _base_loaders)


# ── Template-Globals: Funktionen die list_wrapper.html braucht ────────────────
# (entsprechen den Flask-Context-Processor-Funktionen in core/ui/app.py)

def _module_label(key: str) -> str:
    from core.ui.module_registry import _mod_registry
    m = _mod_registry.get(key)
    return m.label if m else key.replace("_", " ").title()


def _module_has_settings(key: str) -> bool:
    from core.ui.module_registry import _mod_registry
    m = _mod_registry.get(key)
    return bool(m and m.settings_schema)


templates.env.globals["module_label"]        = _module_label
templates.env.globals["module_has_settings"] = _module_has_settings
