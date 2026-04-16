from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from .jobs import run, run_intern, run_extern, run_single  # re-export fuer api/routers/run.py
from .api import router
from .ui import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, ui_router)

try:
    from astrapi.core.modules.scheduler.engine import register_action
    register_action(f"{_KEY}.run_intern", "Rsync: Intern", run_intern, source=_KEY, source_label="Rsync")
    register_action(f"{_KEY}.run_extern", "Rsync: Extern", run_extern, source=_KEY, source_label="Rsync")
except Exception:
    pass
