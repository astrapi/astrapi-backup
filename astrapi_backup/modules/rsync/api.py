# modules/rsync/api.py
from pathlib import Path

from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_backup.modules.rsync.jobs import preview as _preview

KEY = "rsync"
_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"

router = make_htmx_crud_router(KEY, _SCHEMA_PATH, preview_fn=_preview)
