# app/modules/remotes/ui.py
from pathlib import Path

from flask import render_template, request

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from astrapi.core.ui.store import SqliteTableStore

KEY   = "remotes"
_DIR  = Path(__file__).parent
store = SqliteTableStore(KEY)

bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=False,
)


# ── Modulspezifische Extrarouten ──────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<item>/wake")
def wake_modal(item):
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    description  = request.args.get("description", item)
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb="aufwecken (Wake on LAN)",
        confirm_url=f"/api/{KEY}/{item}/wake",
        method="post",
        container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/scan-host-key")
def scan_host_key_modal(item):
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    description  = request.args.get("description", item)
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb="SSH Host Key eintragen (ssh-keyscan)",
        confirm_url=f"/api/{KEY}/{item}/scan-host-key",
        method="post",
        reload_url=f"/ui/{KEY}/content",
        container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/shutdown")
def shutdown_modal(item):
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    description  = request.args.get("description", item)
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb="herunterfahren",
        confirm_url=f"/api/{KEY}/{item}/shutdown",
        method="post",
        container_id=container_id, loading_id=loading_id,
    )
