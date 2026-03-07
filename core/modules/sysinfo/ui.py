"""core/modules/sysinfo/ui.py – Flask-Blueprint für /ui/sysinfo/"""
from flask import Blueprint, render_template
from .engine import collect

bp = Blueprint("sysinfo_ui", __name__)


@bp.route("/ui/sysinfo/content")
def sysinfo_content():
    return render_template("sysinfo/partials/tab.html", info=collect())


@bp.route("/ui/sysinfo/metrics")
def sysinfo_metrics():
    return render_template("sysinfo/partials/metrics.html", info=collect())
