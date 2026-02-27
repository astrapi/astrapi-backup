# api/templates.py  – zentrale Jinja2-Instanz mit allen Filtern
from pathlib import Path
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ── Custom Filter ────────────────────────────────────────────────
