from pathlib import Path

from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.proxmox_jobs.ui.crud import api_router as router
from astrapi_backup.modules.proxmox_jobs.ui.crud import router as ui_router

from .jobs import run, run_by_type, run_single  # run/run_single: re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name
from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402

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
    ui_content=ContentTable(
        columns=[
            Col.badge_enum(
                "type",
                "Typ",
                {
                    "vzdump": {"label": "Backup", "cls": "badge-live"},
                    "sync": {"label": "Sync", "cls": "badge-live"},
                    "verify": {"label": "Verify", "cls": "badge-muted"},
                    "prune": {"label": "Prune", "cls": "badge-warn"},
                },
            ),
            Col.remote_host("remote_id", "Host"),
        ],
    ),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(
        f"{_KEY}.verify",
        "Proxmox Jobs: Verify ausführen",
        lambda: run_by_type("verify"),
        source=_KEY,
        source_label="Proxmox Jobs",
    )
    register_action(f"{_KEY}.prune", "Proxmox Jobs: Prune ausführen", lambda: run_by_type("prune"))
    register_action(f"{_KEY}.sync", "Proxmox Jobs: Sync ausführen", lambda: run_by_type("sync"))
except Exception:
    pass
