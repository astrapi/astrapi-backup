# app/modules/remotes/ui.py
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.render import render

KEY    = "remotes"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)

router = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=False,
    description_field="host",
)


# ── Modulspezifische Extrarouten ──────────────────────────────────────────────

@router.get(f"/ui/{KEY}/{{item}}/wake", response_class=HTMLResponse)
def wake_modal(item: str, request: Request):
    container_id = request.query_params.get("container_id", f"tab-{KEY}")
    loading_id   = request.query_params.get("loading_id",   f"{KEY}-loading")
    description  = request.query_params.get("description", item)
    return render(request, "partials/confirm_modal.html", dict(
        description=description, verb="aufwecken (Wake on LAN)",
        confirm_url=f"/api/{KEY}/{item}/wake",
        method="post",
        container_id=container_id, loading_id=loading_id,
    ))


@router.get(f"/ui/{KEY}/{{item}}/scan-host-key", response_class=HTMLResponse)
def scan_host_key_modal(item: str, request: Request):
    container_id = request.query_params.get("container_id", f"tab-{KEY}")
    loading_id   = request.query_params.get("loading_id",   f"{KEY}-loading")
    description  = request.query_params.get("description", item)
    return render(request, "partials/confirm_modal.html", dict(
        description=description, verb="SSH Host Key eintragen (ssh-keyscan)",
        confirm_url=f"/api/{KEY}/{item}/scan-host-key",
        method="post",
        reload_url=f"/ui/{KEY}/content",
        container_id=container_id, loading_id=loading_id,
    ))


@router.get(f"/ui/{KEY}/{{item}}/shutdown", response_class=HTMLResponse)
def shutdown_modal(item: str, request: Request):
    container_id = request.query_params.get("container_id", f"tab-{KEY}")
    loading_id   = request.query_params.get("loading_id",   f"{KEY}-loading")
    description  = request.query_params.get("description", item)
    return render(request, "partials/confirm_modal.html", dict(
        description=description, verb="herunterfahren",
        confirm_url=f"/api/{KEY}/{item}/shutdown",
        method="post",
        container_id=container_id, loading_id=loading_id,
    ))
