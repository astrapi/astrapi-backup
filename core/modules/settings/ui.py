"""core/modules/settings/ui.py – Flask-Blueprint für Settings UI-Routen."""
from flask import Blueprint, render_template, current_app

KEY = "settings"
bp  = Blueprint(f"{KEY}_ui", __name__)


def _ctx(flash: str = "") -> dict:
    from core.ui.settings_registry import all_settings
    return {
        "settings":      all_settings(),
        "modules":       current_app.config.get("LOADED_MODULES", []),
        "flash_message": flash,
    }


@bp.route(f"/ui/{KEY}/content")
def settings_content():
    return render_template("settings/partials/tab.html", **_ctx())
