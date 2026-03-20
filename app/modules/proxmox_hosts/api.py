# modules/proxmox_hosts/api.py
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from api.storage import get_item
from core.ui.htmx_crud_router import make_htmx_crud_router

KEY = "proxmox_hosts"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _derive_description(payload: dict) -> dict:
    payload["description"] = payload.get("host", "")
    return payload


router = make_htmx_crud_router(KEY, _SCHEMA_PATH, post_process=_derive_description)


@router.get("/{item_id}/preview")
def preview_item(item_id: str, request: Request):
    from modules.proxmox_hosts import jobs
    from api.templates import templates
    entry = get_item(KEY, item_id) or get_item(KEY, int(item_id) if item_id.isdigit() else item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    return templates.TemplateResponse("partials/preview_modal.html", {
        "request":     request,
        "description": entry.get("description", item_id),
        "commands":    jobs.preview(item_id),
    })
