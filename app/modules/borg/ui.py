# app/modules/borg/ui.py
from pathlib import Path
from flask import Blueprint, render_template, request
import yaml

KEY = "borg"
bp  = Blueprint(f"{KEY}_ui", __name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _load_schema():
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


def _resolve_fields(fields: list) -> list:
    from core.ui.field_resolver import resolve_options_endpoint
    return resolve_options_endpoint(fields)


def _list_ctx():
    from api.storage import load_config
    from api.routers.run import get_running
    return dict(
        cfg=load_config(KEY),
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        list_wrapper="partials/list_wrapper.html",
        running=get_running(),
        has_run_buttons=False,
    )


@bp.route(f"/ui/{KEY}/content")
def content():
    return render_template("partials/list_wrapper.html", **_list_ctx())


@bp.route(f"/ui/{KEY}/create")
def create_modal():
    schema = _load_schema()
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    submit_url   = f"/api/{KEY}/create?container_id={container_id}&loading_id={loading_id}"
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=_resolve_fields(schema["fields"]), item=None, method="post", title="Borg Job anlegen",
        submit_url=submit_url, container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/edit")
def edit_modal(item):
    from api.storage import get_item
    schema = _load_schema()
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    values = get_item(KEY, item) or {}
    values.setdefault("pre", [])
    values.setdefault("post", [])
    values.setdefault("exclude", [])
    submit_url = f"/api/{KEY}/{item}/edit?container_id={container_id}&loading_id={loading_id}"
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=_resolve_fields(schema["fields"]), item=values, method="patch", title="Borg Job bearbeiten",
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
        reload_url=f"/ui/{KEY}/content",
        container_id=container_id, loading_id=loading_id,
    )
