from pathlib import Path
from core.ui.module_loader import load_modul
from .ui import bp

module = load_modul(Path(__file__).parent, "settings", None, bp)
