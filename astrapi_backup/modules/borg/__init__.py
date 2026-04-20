from pathlib import Path
from astrapi_core.ui.module_loader import load_modul
from .jobs import run, run_single  # re-export fuer api/routers/run.py
from .api import router
from .ui import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, ui_router)

try:
    from astrapi_core.modules.scheduler.engine import register_action
    register_action(f"{_KEY}.run", "Borg: Backup ausführen", run, source=_KEY, source_label="Borg")
except Exception:
    pass
