# app/modules/borg/ui.py
from pathlib import Path

from flask import render_template, request

from core.ui.crud_blueprint import make_crud_blueprint
from core.ui.store import SqliteTableStore
from core.ui.field_resolver import resolve_options_endpoint

KEY   = "borg"
_DIR  = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Borg Job",
    has_run_buttons=False,
    resolve_fields_fn=_resolve_fields,
)
