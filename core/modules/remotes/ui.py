# core/modules/remotes/ui.py
from pathlib import Path
from flask import Blueprint, render_template, request
import yaml

KEY = "remotes"
bp  = Blueprint(f"{KEY}_ui", __name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _load_schema():
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


@bp.route(f"/ui/{KEY}/content")
def content():
    from core.system.db import load_config
    return render_template("partials/list_wrapper.html",
        cfg=load_config(KEY),
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        running={},
        has_run_buttons=False,
    )


@bp.route(f"/ui/{KEY}/create")
def create_modal():
    schema       = _load_schema()
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    submit_url   = f"/api/{KEY}/create?container_id={container_id}&loading_id={loading_id}"
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=schema["fields"], item=None, method="post", title="Neu",
        submit_url=submit_url, container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/edit")
def edit_modal(item):
    from core.system.db import get_item
    schema       = _load_schema()
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    values       = get_item(KEY, item) or {}
    submit_url   = f"/api/{KEY}/{item}/edit?container_id={container_id}&loading_id={loading_id}"
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=schema["fields"], item=values, method="patch",
        title=f"Bearbeiten: {values.get('description', item)}",
        submit_url=submit_url, container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/toggle")
def toggle_modal(item):
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    enabled      = request.args.get("enabled")
    description  = request.args.get("description", item)
    verb = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb=verb,
        confirm_url=f"/api/{KEY}/{item}/toggle",
        method="post",
        reload_url=f"/ui/{KEY}/content",
        container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/delete")
def delete_modal(item):
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    description  = request.args.get("description", item)
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb="löschen",
        confirm_url=f"/api/{KEY}/{item}/delete",
        method="delete",
        container_id=container_id, loading_id=loading_id,
    )


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
