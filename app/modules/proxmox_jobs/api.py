# modules/proxmox_jobs/api.py
import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Header

from api.storage import load_config, get_item, delete_item, save_item, next_item_id
from api.routers.run import get_running

KEY = "proxmox_jobs"
router = APIRouter()

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _load_schema() -> dict:
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


def _list_response(request: Request):
    from api.templates import templates
    return templates.TemplateResponse(
        "partials/list_wrapper_inner.html",
        {
            "request":          request,
            "cfg":              load_config(KEY),
            "module":           KEY,
            "content_template": f"{KEY}/partials/list.html",
            "container_id":     f"tab-{KEY}",
            "loading_id":       f"{KEY}-loading",
            "running":          get_running(),
        },
    )


def _clean(data: dict) -> dict:
    return {
        k: v for k, v in data.items()
        if v is not None
        and not (isinstance(v, str) and v.strip() == "")
        and not (isinstance(v, list) and len(v) == 0)
    }


def _extract_lists(schema, payload):
    """Gibt (bereinigtes payload, list_values) zurück."""
    fields = schema.get("fields", [])
    list_fields = [f["name"] for f in fields if f.get("type") == "list"]
    lists: dict = {n: [] for n in list_fields}
    for k, v in payload.items():
        for ln in list_fields:
            if k.startswith(f"{ln}_"):
                try:
                    idx = int(k[len(ln) + 1:])
                    lists[ln].append((idx, v))
                except ValueError:
                    pass
    for n in list_fields:
        lists[n] = [v for _, v in sorted(lists[n])]
    prefixes = tuple(f"{n}_" for n in list_fields)
    clean_payload = {k: v for k, v in payload.items() if not any(k.startswith(p) for p in prefixes)}
    # Fehlende Nicht-Listen-Felder auffüllen
    for f in fields:
        if f["name"] not in clean_payload and f.get("type") != "list":
            clean_payload[f["name"]] = ""
    for n in list_fields:
        clean_payload[n] = lists[n]
    return clean_payload


@router.post("/create")
async def create_one(request: Request):
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    payload = _extract_lists(_load_schema(), payload)
    save_item(KEY, next_item_id(KEY), _clean(payload))
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return payload


@router.patch("/{item_id}/edit")
async def patch_one(item_id: str, request: Request):
    iid      = int(item_id)
    existing = get_item(KEY, iid)
    if existing is None:
        raise HTTPException(404, "Item not found")
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    payload  = _extract_lists(_load_schema(), payload)
    existing.update(payload)
    save_item(KEY, iid, _clean(existing))
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return existing


@router.delete("/{item_id}/delete")
def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
    if not delete_item(KEY, item_id):
        raise HTTPException(404, "Item not found")
    if hx_request:
        return _list_response(request)


@router.post("/{item_id}/toggle")
def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
    cfg = load_config(KEY)
    key = item_id
    if key not in cfg:
        try:
            key = int(item_id)
        except ValueError:
            pass
    cfg[key]["enabled"] = not cfg[key].get("enabled", False)
    save_item(KEY, key, cfg[key])
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "item": key, "enabled": cfg[key]["enabled"]}


@router.post("/enable-all")
def enable_all(request: Request):
    for iid, item in load_config(KEY).items():
        if not item.get("enabled", False):
            item["enabled"] = True
            save_item(KEY, iid, item)
    return _list_response(request)


@router.post("/disable-all")
def disable_all(request: Request):
    for iid, item in load_config(KEY).items():
        if item.get("enabled", True):
            item["enabled"] = False
            save_item(KEY, iid, item)
    return _list_response(request)


@router.get("/{item_id}/preview")
def preview_item(item_id: str, request: Request):
    from modules.proxmox_jobs import jobs
    entry = get_item(KEY, item_id) or get_item(KEY, int(item_id) if item_id.isdigit() else item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    from api.templates import templates
    return templates.TemplateResponse("partials/preview_modal.html", {
        "request":     request,
        "description": entry.get("description", item_id),
        "commands":    jobs.preview(item_id),
    })
