# app/modules/browser/ui.py
from flask import Blueprint, render_template

KEY = "browser"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route("/ui/browser/content")
def content():
    from api.storage import list_repos
    return render_template("browser/partials/tab.html", repos=list_repos())
