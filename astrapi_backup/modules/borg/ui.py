# app/modules/borg/ui.py
from pathlib import Path

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint

KEY    = "borg"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


router = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Borg Job",
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
)
