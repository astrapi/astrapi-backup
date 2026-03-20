# modules/proxmox_hosts/api.py
from pathlib import Path

from core.ui.htmx_crud_router import make_htmx_crud_router
from modules.proxmox_hosts.jobs import preview as _preview

KEY = "proxmox_hosts"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _derive_description(payload: dict) -> dict:
    payload["description"] = payload.get("host", "")
    return payload


router = make_htmx_crud_router(KEY, _SCHEMA_PATH, post_process=_derive_description, preview_fn=_preview)
