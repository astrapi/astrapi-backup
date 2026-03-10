from pathlib import Path
from core.ui.module_loader import load_modul
from .jobs import run, run_single  # re-export fuer api/routers/run.py
from .api import router
from .ui import bp

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, bp)

try:
    from core.modules.scheduler.engine import register_action
    register_action(f"{_KEY}.run", "Proxmox LXC sichern", run, source=_KEY, source_label="Proxmox LXC")
except Exception:
    pass
