# app/modules/errors/ui.py
from flask import Blueprint, render_template

KEY = "errors"
bp  = Blueprint(f"{KEY}_ui", __name__)


@bp.route("/ui/errors/content")
def content():
    from helpers.logger import get_all_errors
    return render_template("errors/partials/list.html", errors=get_all_errors())
