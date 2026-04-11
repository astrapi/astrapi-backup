# modules/proxmox_hosts/api.py
from pathlib import Path

from fastapi import APIRouter
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


@router.get("/remotes-for-select")
def remotes_for_select():
    """Gibt proxmox_host-Remotes zurück – ohne 'Lokal' und ohne bereits registrierte."""
    from astrapi.core.system.db import load_config
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select

    registered_ids = {
        str(e.get("remote_id"))
        for e in load_config(KEY).values()
        if e.get("remote_id") is not None
    }

    options = [
        r for r in get_all_remotes_for_select(type_filter="proxmox_host")
        if r["id"] != "local" and str(r["id"]) not in registered_ids
    ]
    return {"options": options}
