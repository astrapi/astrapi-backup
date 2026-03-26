# app/modules/proxmox_jobs/ui.py
from pathlib import Path

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint

KEY   = "proxmox_jobs"
_DIR  = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=False,
    resolve_fields_fn=_resolve_fields,
)
