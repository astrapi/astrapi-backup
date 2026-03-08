# app/modules/settings/ui.py
from flask import Blueprint, render_template

KEY = "settings"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route(f"/ui/{KEY}/content")
def content():
    from api.storage import get_setting
    from helpers.secrets import get_secret_safe
    from core.modules.settings.engine import get_status
    import json

    ntfy_server     = get_setting("ntfy_url", "")
    ntfy_topic      = get_setting("ntfy_topic", "")
    repos_base_path = get_setting("repos_base_path", "/mnt/borg")
    wol_entries     = json.loads(get_setting("wol_entries", "[]"))

    return render_template(
        "settings/partials/tab.html",
        status=get_status(),
        ntfy_server=ntfy_server,
        ntfy_topic=ntfy_topic,
        repos_base_path=repos_base_path,
        wol_entries=wol_entries,
        borg_passphrase_set=bool(get_secret_safe("borg_passphrase")),
        pbs_password_set=bool(get_secret_safe("pbs_password")),
        pbs_fingerprint_set=bool(get_secret_safe("pbs_fingerprint")),
    )
