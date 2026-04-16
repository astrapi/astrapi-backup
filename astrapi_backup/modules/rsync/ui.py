# app/modules/rsync/ui.py
from pathlib import Path

from astrapi.core.ui.crud_blueprint import make_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi.core.ui.store import SqliteTableStore
from astrapi.core.ui.field_resolver import resolve_options_endpoint

KEY    = "rsync"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def _remote_options(type_filter: str, include_local: bool) -> list[dict]:
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select
    return [
        {"value": r["id"], "label": r["label"]}
        for r in get_all_remotes_for_select(type_filter=type_filter, include_local=include_local)
    ]


router = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
    filters=[
        {
            "param":      "type",
            "label":      "Typ",
            "all_label":  "Alle Typen",
            "options_fn": lambda: [
                {"value": "intern", "label": "Intern"},
                {"value": "extern", "label": "Extern"},
            ],
        },
        {
            "param":      "source_remote_id",
            "label":      "Quelle",
            "all_label":  "Alle Quellen",
            "options_fn": lambda: _remote_options("rsync", include_local=True),
        },
        {
            "param":      "target_remote_id",
            "label":      "Ziel",
            "all_label":  "Alle Ziele",
            "options_fn": lambda: _remote_options("rsync", include_local=True),
        },
    ],
)
