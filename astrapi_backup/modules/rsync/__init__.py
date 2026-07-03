from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable, Header
from astrapi_core.ui.module_loader import load_modul

from astrapi_backup.modules.rsync.ui.crud import api_router as router
from astrapi_backup.modules.rsync.ui.crud import router as ui_router

from .jobs import run, run_extern, run_intern, run_single  # re-export fuer api/routers/run.py

_KEY = Path(__file__).parent.name


def _remote_options(type_filter: str, include_local: bool = True) -> list:
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select

    return [
        {"value": r["id"], "label": r["label"]}
        for r in get_all_remotes_for_select(type_filter=type_filter, include_local=include_local)
    ]


module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header([
        Header.filter_select(
            "type",
            [{"value": "intern", "label": "Intern"}, {"value": "extern", "label": "Extern"}],
            all_label="Alle Typen",
        ),
        Header.filter_select(
            "source_remote_id",
            options_fn=lambda: _remote_options("rsync", include_local=True),
            all_label="Alle Quellen",
        ),
        Header.filter_select(
            "target_remote_id",
            options_fn=lambda: _remote_options("rsync", include_local=True),
            all_label="Alle Ziele",
        ),
        Header.filter_select(
            "last_status",
            [
                {"value": "neu", "label": "Neu"},
                {"value": "ok", "label": "OK"},
                {"value": "error", "label": "Fehler"},
            ],
            all_label="Alle Status",
        ),
        Header.action_button("Neu", hx_get=f"/ui/{_KEY}/create", hx_target="body"),
    ]),
    ui_content=ContentTable(
        columns=[
            Col.badge_enum(
                "type",
                "Typ",
                {
                    "intern": {"label": "Intern", "cls": "badge-live"},
                    "extern": {"label": "Extern", "cls": "badge-live"},
                },
            ),
            Col.remote_path("source_remote_id", "source_path", "Quelle"),
            Col.remote_path("target_remote_id", "target_path", "Ziel"),
        ],
    ),
)

try:
    from astrapi_core.modules.scheduler.engine import register_action

    register_action(
        f"{_KEY}.run_intern", "Rsync: Intern", run_intern, source=_KEY, source_label="Rsync"
    )
    register_action(
        f"{_KEY}.run_extern", "Rsync: Extern", run_extern, source=_KEY, source_label="Rsync"
    )
except Exception:
    pass
