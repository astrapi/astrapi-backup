# app/modules/proxmox_hosts/ui.py
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint

KEY    = "proxmox_hosts"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    fields = resolve_options_endpoint(fields)

    # Bereits registrierte Remote-IDs und "local" aus dem Dropdown entfernen
    from astrapi.core.system.db import load_config
    registered_ids = {
        str(e.get("remote_id"))
        for e in load_config(KEY).values()
        if e.get("remote_id") is not None
    }

    result = []
    for field in fields:
        if field.get("name") == "remote_id" and "options" in field:
            field = dict(field)
            field["options"] = [
                opt for opt in field["options"]
                if str(opt.get("value", "")) not in registered_ids
                and str(opt.get("value", "")) != "local"
            ]
        result.append(field)
    return result


def _host_from_remote(remote_id) -> str:
    if not remote_id:
        return ""
    try:
        from astrapi_backup.modules.remotes.engine import get_remote
        r = get_remote(remote_id)
        return r.get("host", "") if r else ""
    except Exception:
        return ""


def _parse_source_list(form) -> list[str]:
    """Liest source_0, source_1, … aus dem Formular."""
    entries = {}
    for k, v in form.multi_items():
        if k.startswith("source_"):
            try:
                idx = int(k[len("source_"):])
                if v.strip():
                    entries[idx] = v.strip()
            except ValueError:
                pass
    return [v for _, v in sorted(entries.items())]


router = APIRouter()


@router.post(f"/ui/{KEY}/", response_class=HTMLResponse)
async def create_apply(request: Request):
    from astrapi.core.ui.render import render
    form        = await request.form()
    remote_id   = form.get("remote_id", "")
    description = _host_from_remote(remote_id)
    data = {
        "description": description,
        "enabled":     form.get("enabled") in ("on", "1", True),
        "remote_id":   remote_id,
        "source":      _parse_source_list(form),
    }
    store.create(None, data)
    cfg = store.list()
    return render(request, "partials/list_wrapper.html", dict(
        cfg=cfg,
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        running=get_running(),
        has_run_buttons=True,
    ))


@router.post(f"/ui/{KEY}/{{item_id}}/update", response_class=HTMLResponse)
async def edit_apply(item_id: str, request: Request):
    from astrapi.core.ui.render import render
    form      = await request.form()
    remote_id = form.get("remote_id", "")
    item      = store.get(item_id) or {}
    item.update({
        "description": _host_from_remote(remote_id) or item.get("description", ""),
        "enabled":     form.get("enabled") in ("on", "1", True),
        "remote_id":   remote_id,
        "source":      _parse_source_list(form),
    })
    store.update(item_id, item)
    cfg = store.list()
    return render(request, "partials/list_wrapper.html", dict(
        cfg=cfg,
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        running=get_running(),
        has_run_buttons=True,
    ))


_crud = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
)
router.include_router(_crud)
