from pathlib import Path
from core.ui.module_loader import load_modul
from .api import router
from .ui import bp

module = load_modul(Path(__file__).parent, "remotes", router, bp)

try:
    from .jobs import sync_all_item_actions
    sync_all_item_actions()
except Exception:
    pass
