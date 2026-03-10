# app/modules/wol/ui.py
from flask import Blueprint, render_template

KEY = "wol"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route(f"/ui/{KEY}/content")
def content():
    from core.ui.settings_registry import get_module
    entries = get_module("wol", "entries", []) or []
    return render_template("wol/partials/tab.html", wol_entries=entries)
