# app/modules/history/ui.py
from flask import Blueprint, render_template, request

KEY = "history"
bp  = Blueprint(f"{KEY}_ui", __name__)


def _fmt_duration(s):
    if s is None:
        return "—"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, min_ = divmod(m, 60)
    return f"{h}h {min_}m"


@bp.route("/ui/history/content")
def content():
    from api.storage import list_history
    module = request.args.get("module", "")
    entries = list_history(limit=200, module=module or None)
    for e in entries:
        e["duration_fmt"] = _fmt_duration(e.get("duration_s"))
    return render_template(
        "history/partials/tab.html",
        entries=entries,
        filter_module=module,
        modules=["borg", "rsync", "proxmox_lxc", "proxmox_hosts", "proxmox_jobs"],
    )
