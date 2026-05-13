from pathlib import Path

from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.proxmox_hosts.ui.crud import api_router as router
from astrapi_backup.modules.proxmox_hosts.ui.crud import router as ui_router

from .jobs import run, run_single  # re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name
module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    # proxmox_hosts: keine modul-spezifischen Spalten (list_header.html ist leer)
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(
        f"{_KEY}.run", "Proxmox Hosts: Sichern", run, source=_KEY, source_label="Proxmox Hosts"
    )
except Exception:
    pass
