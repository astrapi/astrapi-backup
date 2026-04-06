from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from .jobs import run, run_single, run_by_type  # run/run_single: re-export fuer api/routers/run.py
from .api import router
from .ui import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, ui_router)

try:
    from astrapi.core.modules.scheduler.engine import register_action
    register_action(f"{_KEY}.verify", "Proxmox Jobs: Verify ausführen",  lambda: run_by_type("verify"), source=_KEY, source_label="Proxmox Jobs")
    register_action(f"{_KEY}.prune",  "Proxmox Jobs: Prune ausführen",   lambda: run_by_type("prune"))
    register_action(f"{_KEY}.sync",   "Proxmox Jobs: Sync ausführen",    lambda: run_by_type("sync"))
except Exception:
    pass
