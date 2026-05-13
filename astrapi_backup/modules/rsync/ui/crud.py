# modules/rsync/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore

from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.rsync.jobs import preview as _preview

KEY = "rsync"
_DIR = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def _remote_options(type_filter: str, include_local: bool) -> list[dict]:
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select

    return [
        {"value": r["id"], "label": r["label"]}
        for r in get_all_remotes_for_select(type_filter=type_filter, include_local=include_local)
    ]


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR.parent / "config" / "schema.yaml"),
    has_run_buttons=True,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
    create_defaults={"last_status": "neu"},
    filters=[
        {
            "param": "type",
            "label": "Typ",
            "all_label": "Alle Typen",
            "options_fn": lambda: [
                {"value": "intern", "label": "Intern"},
                {"value": "extern", "label": "Extern"},
            ],
        },
        {
            "param": "source_remote_id",
            "label": "Quelle",
            "all_label": "Alle Quellen",
            "options_fn": lambda: _remote_options("rsync", include_local=True),
        },
        {
            "param": "target_remote_id",
            "label": "Ziel",
            "all_label": "Alle Ziele",
            "options_fn": lambda: _remote_options("rsync", include_local=True),
        },
        {
            "param": "last_status",
            "label": "Status",
            "all_label": "Alle Status",
            "options_fn": lambda: [
                {"value": "neu", "label": "Neu"},
                {"value": "ok", "label": "OK"},
                {"value": "error", "label": "Fehler"},
            ],
        },
    ],
)

_SCHEMA_PATH = _DIR.parent / "config" / "schema.yaml"
api_router = make_htmx_crud_router(KEY, _SCHEMA_PATH, preview_fn=_preview, running_fn=get_running)
