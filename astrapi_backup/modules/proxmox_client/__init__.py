from pathlib import Path

from astrapi_core.ui.controls import Header
from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.proxmox_client.ui.crud import api_router as router
from astrapi_backup.modules.proxmox_client.ui.crud import router as ui_router

from .jobs import run, run_single  # re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name
module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.filter_select(
            "last_status",
            [
                {"value": "neu", "label": "Neu"},
                {"value": "ok", "label": "OK"},
                {"value": "error", "label": "Fehler"},
            ],
            all_label="Alle Status",
        ),
        Header.action_button("Neu", hx_get=f"/ui/{_KEY}/create", hx_target="body"),
    ]),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(
        f"{_KEY}.run", "Proxmox Client: Sichern", run, source=_KEY, source_label="Proxmox Client"
    )
except Exception:
    pass
