# app/modules/repos/ui.py
import os, subprocess, json
from pathlib import Path
from flask import Blueprint, render_template, request

KEY = "repos"
bp  = Blueprint(f"{KEY}_ui", __name__)

BORG = "/var/lib/backupadm/.venv/bin/borg"


def _borg_env(repo_id: int) -> dict:
    from helpers.secrets import get_secret_safe
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = (
        get_secret_safe(f"BORG_PASSPHRASE_{repo_id}") or
        get_secret_safe("BORG_PASSPHRASE", "")
    )
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env


def _borg_info(path: str, env: dict) -> dict:
    try:
        r = subprocess.run([BORG, "info", "--json", path],
                           capture_output=True, text=True, timeout=60, env=env)
        if r.returncode == 0:
            return json.loads(r.stdout)
    except Exception:
        pass
    return {}


def _borg_list(path: str, env: dict) -> list:
    try:
        r = subprocess.run([BORG, "list", "--json", path],
                           capture_output=True, text=True, timeout=60, env=env)
        if r.returncode == 0:
            archives = json.loads(r.stdout).get("archives", [])
            archives.sort(key=lambda a: a.get("time", ""), reverse=True)
            return archives
    except Exception:
        pass
    return []


def _fmt_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


@bp.route("/ui/repos/content")
def content():
    from api.storage import list_repos
    repos = list_repos()
    for repo in repos:
        env = _borg_env(repo["id"])
        info = _borg_info(repo["path"], env)
        cache = info.get("cache", {}).get("stats", {})
        repo["total_size"]    = _fmt_size(cache.get("total_size", 0))
        repo["total_csize"]   = _fmt_size(cache.get("total_csize", 0))
        repo["num_archives"]  = cache.get("total_chunks", None)
        archives = _borg_list(repo["path"], env)
        repo["archive_count"] = len(archives)
        repo["last_archive"]  = archives[0]["time"][:16].replace("T", " ") if archives else "—"
        repo["reachable"]     = bool(info)
    return render_template("repos/partials/tab.html", repos=repos)
