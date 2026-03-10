# core/modules/scheduler/ui.py
from flask import Blueprint, render_template, request

bp = Blueprint("scheduler_ui", __name__)


def _render(flash: str = ""):
    from core.modules.scheduler.engine import get_config, is_configured
    return render_template(
        "scheduler/partials/tab.html",
        config=get_config(),
        configured=is_configured(),
        flash_message=flash,
    )


@bp.route("/ui/scheduler/content")
def scheduler_content():
    return _render()


@bp.route("/ui/scheduler/save", methods=["POST"])
def scheduler_save():
    from core.modules.scheduler.engine import update_config
    cron    = request.form.get("cron", "").strip()
    enabled = request.form.get("enabled") == "1"
    update_config(cron=cron or None, enabled=enabled)
    return _render("Gespeichert.")


@bp.route("/ui/scheduler/trigger", methods=["POST"])
def scheduler_trigger():
    from core.modules.scheduler.engine import trigger_now, is_configured
    debug = request.form.get("debug") == "1"
    if is_configured():
        trigger_now(debug=debug)
    return _render("Job gestartet.")
