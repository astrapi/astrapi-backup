# app/modules/settings/ui.py
from flask import Blueprint, render_template

KEY = "settings"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route(f"/ui/{KEY}/content")
def content():
    from core.ui.settings_registry import get_module
    from helpers.secrets import get_secret_safe
    from core.modules.settings.engine import get_status

    repos_base_path = get_module("repos", "base_path", "/mnt/borg")

    return render_template(
        "settings/partials/tab.html",
        status=get_status(),
        repos_base_path=repos_base_path,
        borg_passphrase_set=bool(get_secret_safe("BORG_PASSPHRASE")),
        pbs_password_set=bool(get_secret_safe("PBS_PASSWORD")),
        pbs_fingerprint_set=bool(get_secret_safe("PBS_FINGERPRINT")),
    )
