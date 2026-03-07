from pathlib import Path
from core.ui.module_loader import load_modul
from .ui import bp
from .api import router as api_router

module = load_modul(Path(__file__).parent, "errors", api_router, bp)
