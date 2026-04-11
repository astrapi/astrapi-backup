# app/modules/proxmox_lxc/ui.py
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint
from astrapi.core.ui.settings_registry import get_module as _get_module

KEY    = "proxmox_lxc"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    """Ersetzt options_from_settings und options_endpoint durch echte Werte."""
    result = []
    for field in fields:
        if "options_from_settings" in field:
            settings_key = field["options_from_settings"]
            nodes = _get_module(KEY, settings_key, []) or []
            field = dict(field)
            field["options"] = [{"value": n, "label": n} for n in nodes if n]
            del field["options_from_settings"]
        result.append(field)
    return resolve_options_endpoint(result)


# Eigene Routen zuerst registrieren – FastAPI nutzt first-match
router = APIRouter()


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    from astrapi.core.ui.render import render
    return render(request, "proxmox_lxc/partials/create_modal.html", dict(
        loading_id=request.query_params.get("loading_id", f"{KEY}-loading"),
    ))


@router.get(f"/ui/{KEY}/available-select", response_class=HTMLResponse)
def available_select(request: Request):
    from astrapi.core.ui.render import render
    from astrapi_backup.modules.proxmox_lxc.api import fetch_available_lxc
    available = []
    try:
        available = fetch_available_lxc()
    except Exception:
        pass
    return render(request, "proxmox_lxc/partials/available_select.html", {"available": available})


# Generische CRUD-Routen danach (create wird durch obige Route überschattet)
_crud = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
)
router.include_router(_crud)
