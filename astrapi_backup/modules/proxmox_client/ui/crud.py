# modules/proxmox_client/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_client.jobs import preview as _preview

KEY = "proxmox_client"
_DIR = Path(__file__).parent
store = SqliteTableStore(KEY)

_MODAL_WIDTH = 600
_C_ID = f"mod-{KEY}"
_L_ID = f"{KEY}-loading"


def _derive_description(payload: dict) -> dict:
    remote_id = payload.get("remote_id")
    if remote_id:
        from astrapi_backup.modules.remotes.service import get_remote

        r = get_remote(remote_id)
        payload["description"] = r.get("host", "") if r else ""
    return payload


def _available_host_options(exclude_ids: set[str] | None = None) -> list[dict]:
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select

    remotes = get_all_remotes_for_select(type_filter="proxmox_host", include_local=False)
    return sorted(
        [
            {"value": r["id"], "label": r["label"]}
            for r in remotes
            if exclude_ids is None or str(r["id"]) not in exclude_ids
        ],
        key=lambda o: (o["label"] or "").lower(),
    )


def _registered_remote_ids() -> set[str]:
    from astrapi_core.system.db import load_config

    return {
        str(e.get("remote_id")) for e in load_config(KEY).values() if e.get("remote_id") is not None
    }


def _description_from_remote(remote_id: str) -> str:
    if not remote_id:
        return ""
    try:
        from astrapi_backup.modules.remotes.service import get_remote

        r = get_remote(remote_id)
        return r.get("host", "") if r else ""
    except Exception:
        return ""


router = APIRouter()


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    from astrapi_core.ui.render import render

    options = _available_host_options(exclude_ids=_registered_remote_ids())
    if options:
        schema = [
            {
                "name": "remote_id",
                "type": "select",
                "label": "Proxmox Host",
                "options": options,
                "row": 1,
            },
            {"name": "enabled", "type": "boolean", "label": "Aktiviert"},
            {"name": "source", "type": "list", "label": "Zusätzliche Quellen", "row": 2},
        ]
        error = None
    else:
        schema = []
        error = (
            "Keine Remote-Geräte mit dem Typ »Proxmox Host« konfiguriert. "
            "Bitte zuerst ein Remote-Gerät mit diesem Typ anlegen."
        )
    return render(
        request,
        "partials/create_edit/create_edit_modal.html",
        dict(
            schema=schema,
            id_field=None,
            modal_width=_MODAL_WIDTH,
            item=None,
            item_id=None,
            submit_url=f"/ui/{KEY}/",
            method="post",
            title="Neuer Proxmox Host",
            reload_url=f"/ui/{KEY}/content",
            container_id=request.query_params.get("container_id", _C_ID),
            loading_id=request.query_params.get("loading_id", _L_ID),
            prefill_template=None,
            error=error,
        ),
    )


@router.get(f"/ui/{KEY}/{{item_id}}/edit", response_class=HTMLResponse)
def edit_modal(item_id: str, request: Request):
    from astrapi_core.ui.render import render

    item = store.get(item_id)
    if item is None:
        return HTMLResponse("Proxmox Host nicht gefunden", status_code=404)
    fields = [
        {"name": "description", "type": "info", "label": "Host", "row": 1},
        {"name": "enabled", "type": "boolean", "label": "Aktiviert"},
        {"name": "source", "type": "list", "label": "Zusätzliche Quellen", "row": 2},
    ]
    return render(
        request,
        "partials/create_edit/create_edit_modal.html",
        dict(
            schema=fields,
            id_field="id",
            modal_width=_MODAL_WIDTH,
            item=item,
            item_id=item_id,
            submit_url=f"/ui/{KEY}/{item_id}/update",
            method="post",
            title="Proxmox Host bearbeiten",
            reload_url=f"/ui/{KEY}/content",
            container_id=request.query_params.get("container_id", _C_ID),
            loading_id=request.query_params.get("loading_id", _L_ID),
            prefill_template=None,
        ),
    )


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    from astrapi_core.ui.crud_blueprint import resolve_filters_for_request
    from astrapi_core.ui.render import render

    form = await request.form()
    remote_id = form.get("remote_id", "")
    if not remote_id:
        return HTMLResponse("Kein Proxmox Host ausgewählt.", status_code=400)
    data = {
        "description": _description_from_remote(remote_id),
        "enabled": "enabled" in form,
        "remote_id": remote_id,
        "source": list(form.getlist("source")),
    }
    store.create(None, data)
    cfg = store.list()
    cfg, extra = resolve_filters_for_request(KEY, request, cfg)
    return render(
        request,
        "content.html",
        dict(
            cfg=cfg,
            module=KEY,
            container_id=_C_ID,
            loading_id=_L_ID,
            running=get_running(),
            has_run_buttons=True,
            **extra,
        ),
    )


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    from astrapi_core.ui.crud_blueprint import resolve_filters_for_request
    from astrapi_core.ui.render import render

    form = await request.form()
    item = store.get(item_id) or {}
    item.update(
        {
            "enabled": "enabled" in form,
            "source": list(form.getlist("source")),
        }
    )
    store.update(item_id, item)
    cfg = store.list()
    cfg, extra = resolve_filters_for_request(KEY, request, cfg)
    return render(
        request,
        "content.html",
        dict(
            cfg=cfg,
            module=KEY,
            container_id=_C_ID,
            loading_id=_L_ID,
            running=get_running(),
            has_run_buttons=True,
            **extra,
        ),
    )


_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR.parent / "config" / "schema.yaml"),
    has_run_buttons=True,
    has_toggle=False,
    running_fn=get_running,
    create_defaults={"last_status": "neu"},
    filters=[
        {
            "param": "last_status",
            "label": "Status",
            "all_label": "Alle Status",
            "options_fn": lambda: [
                {"value": "neu", "label": "Neu"},
                {"value": "ok", "label": "OK"},
                {"value": "error", "label": "Fehler"},
            ],
        },
    ],
)
router.include_router(_crud)

_SCHEMA_PATH = _DIR.parent / "config" / "schema.yaml"
api_router = make_htmx_crud_router(
    KEY, _SCHEMA_PATH, post_process=_derive_description, preview_fn=_preview, running_fn=get_running
)
