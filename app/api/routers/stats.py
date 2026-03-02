# api/routers/stats.py
# Statistik-Seite: Borg-Repository-Metriken über Zeit

import os
import subprocess
import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.templates import templates
from api.storage import list_repos, get_repo
from helpers.secrets import get_secret_safe

router = APIRouter(tags=["stats"])

BORG = "/var/lib/backupadm/.venv/bin/borg"


def _borg_env(repo_id: int) -> dict:
    env = dict(os.environ)
    passphrase = (
        get_secret_safe(f"BORG_PASSPHRASE_{repo_id}")
        or get_secret_safe("BORG_PASSPHRASE", "")
    )
    env["BORG_PASSPHRASE"] = passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env


def _fmt_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _borg_info(path: str, env: dict) -> dict:
    try:
        r = subprocess.run(
            [BORG, "info", "--json", path],
            capture_output=True, text=True, timeout=60, env=env
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
    except Exception:
        pass
    return {}


def _borg_list(path: str, env: dict) -> list:
    """Gibt Liste aller Archive mit Statistiken zurück."""
    try:
        r = subprocess.run(
            [BORG, "list", "--json", "--format",
             "{name}{TAB}{time}{TAB}{stats[original_size]}{TAB}{stats[compressed_size]}{TAB}{stats[deduplicated_size]}{NL}",
             path],
            capture_output=True, text=True, timeout=60, env=env
        )
        if r.returncode != 0:
            # Fallback: ohne --format (ältere Borg-Versionen)
            r = subprocess.run(
                [BORG, "list", "--json", path],
                capture_output=True, text=True, timeout=60, env=env
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                archives = data.get("archives", [])
                archives.sort(key=lambda a: a.get("time", ""))
                return archives
            return []
        data = json.loads(r.stdout)
        archives = data.get("archives", [])
        archives.sort(key=lambda a: a.get("time", ""))
        return archives
    except Exception:
        return []


def _build_chart_data(archives: list) -> dict:
    """Bereitet Chart.js-kompatible Datensätze auf."""
    labels = []
    orig_sizes   = []
    comp_sizes   = []
    dedup_sizes  = []

    for a in archives:
        t = a.get("time", "")[:16].replace("T", " ")
        labels.append(t)
        stats = a.get("stats", {})
        orig  = stats.get("original_size", 0)
        comp  = stats.get("compressed_size", 0)
        dedup = stats.get("deduplicated_size", 0)
        # In GB für bessere Lesbarkeit im Chart
        orig_sizes.append(round(orig  / (1024**3), 3))
        comp_sizes.append(round(comp  / (1024**3), 3))
        dedup_sizes.append(round(dedup / (1024**3), 3))

    return {
        "labels":      labels,
        "orig_sizes":  orig_sizes,
        "comp_sizes":  comp_sizes,
        "dedup_sizes": dedup_sizes,
    }


def _avg_duration(repo_id: int) -> str:
    """Durchschnittliche Backup-Dauer aus Job-History (letzte 10 Borg-Läufe)."""
    try:
        from api.storage import list_history
        entries = [e for e in list_history(limit=50, module="borg")
                   if e.get("duration_s") and e.get("status") == "ok"][:10]
        if not entries:
            return "—"
        avg = sum(e["duration_s"] for e in entries) / len(entries)
        if avg < 60: return f"{int(avg)}s"
        m, s = divmod(int(avg), 60)
        return f"{m}m {s}s"
    except Exception:
        return "—"


def _repo_stats(repo: dict) -> dict:
    """Alle Statistiken für ein Repo."""
    env      = _borg_env(repo["id"])
    info     = _borg_info(repo["path"], env)
    archives = _borg_list(repo["path"], env)

    cache = info.get("cache", {}).get("stats", {})
    total_orig  = cache.get("total_size", 0)
    total_comp  = cache.get("total_csize", 0)
    total_dedup = cache.get("unique_size", 0)

    comp_ratio  = f"{(1 - total_comp/total_orig)*100:.1f}%" if total_orig > 0 else "—"
    dedup_ratio = f"{(1 - total_dedup/total_orig)*100:.1f}%" if total_orig > 0 else "—"

    # Letzte 30 Archive für Tabelle (neueste zuerst)
    recent = list(reversed(archives[-30:]))

    chart = _build_chart_data(archives[-60:])  # max 60 Datenpunkte

    # Durchschnittliche Archivgröße
    if archives:
        avg_orig = sum(
            a.get("stats", {}).get("original_size", 0) for a in archives
        ) / len(archives)
    else:
        avg_orig = 0

    return {
        "repo":         repo,
        "reachable":    bool(info),
        "archive_count": len(archives),
        "total_orig":   _fmt_size(total_orig),
        "total_comp":   _fmt_size(total_comp),
        "total_dedup":  _fmt_size(total_dedup),
        "comp_ratio":   comp_ratio,
        "dedup_ratio":  dedup_ratio,
        "avg_orig":     _fmt_size(avg_orig),
        "recent":       recent,
        "chart":        chart,
        "avg_duration":  _avg_duration(repo["id"]),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tab", response_class=HTMLResponse)
def stats_tab(request: Request):
    repos = list_repos()
    # Ersten erreichbaren Repo als Default
    default_id = repos[0]["id"] if repos else None
    return templates.TemplateResponse("partials/stats/tab.html", {
        "request":    request,
        "repos":      repos,
        "default_id": default_id,
    })


@router.get("/{repo_id}", response_class=HTMLResponse)
def stats_repo(request: Request, repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", status_code=404)
    data = _repo_stats(repo)
    all_repos = list_repos()
    return templates.TemplateResponse("partials/stats/repo.html", {
        "request":   request,
        "all_repos": all_repos,
        **data,
    })
