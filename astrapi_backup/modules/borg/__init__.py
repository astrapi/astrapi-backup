from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.module_loader import load_modul

from .jobs import run, run_single  # re-export fuer api/routers/run.py
from .ui.archives import router
from .ui.crud import router as ui_router

_KEY = Path(__file__).parent.name
module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_content=ContentTable(
        columns=[
            Col.remote_path("source_remote_id", "source_path", "Quelle"),
            Col.remote_path("target_remote_id", "target_path", "Ziel"),
        ],
    ),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(f"{_KEY}.run", "Borg: Backup ausführen", run, source=_KEY, source_label="Borg")
except Exception:
    pass
