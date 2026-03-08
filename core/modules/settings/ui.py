# core/modules/settings/ui.py
from flask import Blueprint, render_template, current_app

KEY = "settings"
bp  = Blueprint(f"{KEY}_core_ui", __name__)


def _ctx(flash: str = "") -> dict:
    from core.ui.settings_registry import all_settings
    return {
        "settings":      all_settings(),
        "app_cfg":       {k: current_app.config.get(k) for k in
                          ("APP_NAME", "APP_VERSION", "APP_LANG")},
        "flash_message": flash,
    }


@bp.route(f"/ui/{KEY}/content")
def settings_content():
    return render_template("partials/lists/settings.html", **_ctx())
