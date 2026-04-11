# app/modules/proxmox_jobs/ui.py
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint

KEY  = "proxmox_jobs"
_DIR = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


# Eigene Routen zuerst registrieren – FastAPI nutzt first-match
router = APIRouter()


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    from astrapi.core.ui.render import render
    return render(request, "proxmox_jobs/partials/create_modal.html", dict(
        loading_id=request.query_params.get("loading_id", f"{KEY}-loading"),
    ))


@router.get(f"/ui/{KEY}/available-select", response_class=HTMLResponse)
def available_select(request: Request):
    from astrapi.core.ui.render import render
    from astrapi_backup.modules.proxmox_jobs.api import fetch_available_jobs
    available = []
    try:
        available = fetch_available_jobs()
    except Exception:
        pass
    return render(request, "proxmox_jobs/partials/available_select.html", {"available": available})


# Generische CRUD-Routen danach (create wird durch obige Route überschattet)
_crud = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
)
router.include_router(_crud)
