from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable, Header
from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.proxmox_lxc.ui.crud import api_router as router
from astrapi_backup.modules.proxmox_lxc.ui.crud import router as ui_router

from .jobs import run, run_single  # re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name


def _node_options() -> list:
    from astrapi_backup.modules.remotes.service import get_remote

    nodes = sorted({item.get("node") for item in store.list().values() if item.get("node")})

    def _label(node_id: str) -> str:
        try:
            r = get_remote(node_id)
            return r.get("host") or node_id if r else node_id
        except Exception:
            return node_id

    return [{"value": n, "label": _label(n)} for n in nodes]


module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.filter_select("node", options_fn=_node_options, all_label="Alle Nodes"),
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
