from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.proxmox_lxc.ui.crud import api_router as router
from astrapi_backup.modules.proxmox_lxc.ui.crud import router as ui_router

from .jobs import run, run_single  # re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name
module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_content=ContentTable(
        columns=[
            Col.text("vmid", "CT-ID", css="col-type"),
            Col.remote_host("node", "Node"),
        ],
    ),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(
        f"{_KEY}.run", "Proxmox LXC: Sichern", run, source=_KEY, source_label="Proxmox LXC"
    )
except Exception:
    pass
