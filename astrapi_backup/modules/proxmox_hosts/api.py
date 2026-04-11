# modules/proxmox_hosts/api.py
from pathlib import Path

from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_hosts.jobs import preview as _preview

KEY = "proxmox_hosts"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _derive_description(payload: dict) -> dict:
    remote_id = payload.get("remote_id")
    if remote_id:
        from astrapi_backup.modules.remotes.engine import get_remote
        r = get_remote(remote_id)
        payload["description"] = r.get("host", "") if r else ""
    return payload


router = make_htmx_crud_router(KEY, _SCHEMA_PATH, post_process=_derive_description, preview_fn=_preview, running_fn=get_running)
