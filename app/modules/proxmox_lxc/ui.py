# app/modules/proxmox_lxc/ui.py
from pathlib import Path

from core.ui.crud_blueprint import make_crud_blueprint
from core.ui.store import SqliteTableStore
from core.ui.field_resolver import resolve_options_endpoint
from core.ui.settings_registry import get_module as _get_module

KEY   = "proxmox_lxc"
_DIR  = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    """Ersetzt options_from_settings und options_endpoint durch echte Werte."""
    result = []
    for field in fields:
        if "options_from_settings" in field:
            settings_key = field["options_from_settings"]
            nodes = _get_module(KEY, settings_key, []) or []
            field = dict(field)
            field["options"] = [{"value": n, "label": n} for n in nodes if n]
            del field["options_from_settings"]
        result.append(field)
    return resolve_options_endpoint(result)


bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=False,
    resolve_fields_fn=_resolve_fields,
)
