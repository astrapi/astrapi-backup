# api/templates.py – zentrale Jinja2-Instanz mit ChoiceLoader (app/ > core/)
from pathlib import Path
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

# app/ ist der Arbeitsordner (Python-Root beim Start via app/main.py)
# core/ liegt eine Ebene darüber: app/../core/
_APP_ROOT       = Path(__file__).resolve().parent.parent          # = app/
_PROJECT_ROOT   = _APP_ROOT.parent                                # = backupctl/
_APP_TEMPLATES  = _APP_ROOT      / "templates"
_CORE_TEMPLATES = _PROJECT_ROOT  / "core" / "templates"

templates = Jinja2Templates(directory=str(_APP_TEMPLATES))
templates.env.loader = ChoiceLoader([
    FileSystemLoader(str(_APP_TEMPLATES)),
    FileSystemLoader(str(_CORE_TEMPLATES)),
])

# ── Custom Filter ────────────────────────────────────────────────
