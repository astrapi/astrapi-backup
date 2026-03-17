# app/modules/proxmox_lxc/ui.py
from pathlib import Path
from flask import Blueprint, render_template, request
import yaml

KEY = "proxmox_lxc"
bp  = Blueprint(f"{KEY}_ui", __name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


def _load_schema():
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


def _resolve_fields(fields: list) -> list:
    """Ersetzt options_from_settings durch echte Werte aus den Modul-Settings."""
    from core.ui.settings_registry import get_module as _get_module
    result = []
    for field in fields:
        if "options_from_settings" in field:
            key = field["options_from_settings"]
            nodes = _get_module(KEY, key, []) or []
            field = dict(field)
            field["options"] = [{"value": n, "label": n} for n in nodes if n]
            del field["options_from_settings"]
        result.append(field)
    return result


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
        schema=_resolve_fields(schema["fields"]),
        modal_width=schema.get("modal_width", 620),
        item=None, method="post", title="Neu",
        submit_url=submit_url, container_id=container_id, loading_id=loading_id,
    )


@bp.route(f"/ui/{KEY}/<item>/edit")
def edit_modal(item):
    from api.storage import get_item
    schema = _load_schema()
    container_id = request.args.get("container_id", f"tab-{KEY}")
    loading_id   = request.args.get("loading_id",   f"{KEY}-loading")
    values = get_item(KEY, item) or {}
    submit_url = f"/api/{KEY}/{item}/edit?container_id={container_id}&loading_id={loading_id}"
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=_resolve_fields(schema["fields"]),
        modal_width=schema.get("modal_width", 620),
        item=values, method="patch", title=f"Bearbeiten: {item}",
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
