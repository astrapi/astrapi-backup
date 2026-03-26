from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from .jobs import run, run_single  # re-export fuer api/routers/run.py
from .api import router
from .ui import bp

_KEY = Path(__file__).parent.name
module = load_modul(Path(__file__).parent, _KEY, router, bp)

try:
    from astrapi.core.modules.scheduler.engine import register_action
    register_action(f"{_KEY}.run", "Borg: Backup ausführen", run, source=_KEY, source_label="Borg")
except Exception:
    pass
