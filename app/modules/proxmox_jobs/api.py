# modules/proxmox_jobs/api.py
from pathlib import Path

from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
from modules.proxmox_jobs.jobs import preview as _preview

KEY = "proxmox_jobs"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"

router = make_htmx_crud_router(KEY, _SCHEMA_PATH, preview_fn=_preview)
