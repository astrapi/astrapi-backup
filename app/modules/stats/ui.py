# app/modules/stats/ui.py
from flask import Blueprint, render_template

KEY = "stats"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route("/ui/stats/content")
def content():
    from api.storage import list_repos
    repos = list_repos()
    default_id = repos[0]["id"] if repos else None
    return render_template("stats/partials/list.html", repos=repos, default_id=default_id)
