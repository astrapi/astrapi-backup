# api/routers/browser.py
# Archiv-Browser – OHNE FUSE
# Verzeichnisstruktur via borg list --json-lines (alle Einträge einmal laden,
# dann im Backend als virtuelle Verzeichnisansicht navigieren)
# Download einzelner Dateien via borg extract --stdout

import os
import json
import subprocess
from pathlib import PurePosixPath

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from api.templates import templates
from api.storage import list_repos, get_repo
from helpers.secrets import get_secret_safe

router = APIRouter(tags=["browser"])

BORG = "/var/lib/backupadm/.venv/bin/borg"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(repo_id: int) -> dict:
    e = dict(os.environ)
    e["BORG_PASSPHRASE"] = (
        get_secret_safe(f"BORG_PASSPHRASE_{repo_id}") or
        get_secret_safe("BORG_PASSPHRASE", "")
    )
    e["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return e


def _fmt(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def _load_entries(repo_path: str, archive: str, env: dict) -> list[dict]:
    """Ladet alle Einträge eines Archivs via borg list --json-lines."""
    r = subprocess.run(
        [BORG, "list", "--json-lines", f"{repo_path}::{archive}"],
        capture_output=True, text=True, timeout=120, env=env
    )
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _dir_view(entries: list[dict], cur: str) -> tuple[list, list]:
    """
    Baut für den aktuellen Pfad `cur` (ohne führenden Slash) die direkten
    Kinder als (dirs, files) auf.
    dirs:  [{name, path, mtime}]
    files: [{name, path, size_fmt, mtime, mode}]
    """
    dirs_seen: set[str] = set()
    dirs:  list[dict] = []
    files: list[dict] = []

    for entry in entries:
        p = entry.get("path", "").lstrip("/")
        if not p or p == ".":
            continue

        if cur:
            if not p.startswith(cur + "/"):
                continue
            rest = p[len(cur) + 1:]
        else:
            rest = p

        if not rest:
            continue

        parts = rest.split("/")
        child  = parts[0]
        full   = (cur + "/" + child).lstrip("/")
        is_dir = entry.get("type") in ("d", "D") or len(parts) > 1

        if len(parts) > 1:
            # tieferes Element → nur Unterordner zeigen
            if full not in dirs_seen:
                dirs_seen.add(full)
                dirs.append({"name": child, "path": full, "mtime": ""})
        else:
            if is_dir:
                if full not in dirs_seen:
                    dirs_seen.add(full)
                    dirs.append({
                        "name":  child,
                        "path":  full,
                        "mtime": entry.get("mtime", "")[:16].replace("T", " "),
                    })
            else:
                files.append({
                    "name":     child,
                    "path":     p,
                    "size_fmt": _fmt(entry.get("size", 0)),
                    "size":     entry.get("size", 0),
                    "mtime":    entry.get("mtime", "")[:16].replace("T", " "),
                    "mode":     entry.get("mode", ""),
                })

    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    return dirs, files


def _crumbs(cur: str) -> list[dict]:
    crumbs = [{"label": "Archiv-Wurzel", "path": ""}]
    acc = ""
    for part in PurePosixPath(cur).parts if cur else []:
        acc = (acc + "/" + part).lstrip("/")
        crumbs.append({"label": part, "path": acc})
    return crumbs


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tab", response_class=HTMLResponse)
def browser_tab(request: Request):
    return templates.TemplateResponse("browser/partials/tab.html", {
        "request": request,
        "repos":   list_repos(),
    })


@router.get("/{repo_id}/archives", response_class=HTMLResponse)
def browser_archives(request: Request, repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", 404)
    env = _env(repo_id)
    try:
        r = subprocess.run(
            [BORG, "list", "--json", repo["path"]],
            capture_output=True, text=True, timeout=30, env=env
        )
        archives = json.loads(r.stdout).get("archives", []) if r.returncode == 0 else []
        archives = sorted(archives, key=lambda a: a.get("time", ""), reverse=True)
        error = None
    except Exception as e:
        archives = []
        error = str(e)
    return templates.TemplateResponse("browser/partials/archives.html", {
        "request":  request,
        "repo":     repo,
        "archives": archives,
        "error":    error,
    })


@router.get("/{repo_id}/{archive}/browse", response_class=HTMLResponse)
def browser_browse(request: Request, repo_id: int, archive: str, path: str = ""):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", 404)

    cur = path.strip("/")
    env = _env(repo_id)

    entries = _load_entries(repo["path"], archive, env)
    if not entries and not cur:
        return templates.TemplateResponse("browser/partials/browse.html", {
            "request": request, "repo": repo, "archive": archive,
            "path": cur, "breadcrumbs": _crumbs(cur),
            "dirs": [], "files": [], "parent_path": None,
            "error": "Archiv konnte nicht gelesen werden oder ist leer.",
            "total": 0,
        })

    dirs, files = _dir_view(entries, cur)

    parent_path: str | None
    if cur:
        p = str(PurePosixPath(cur).parent)
        parent_path = "" if p == "." else p
    else:
        parent_path = None

    return templates.TemplateResponse("browser/partials/browse.html", {
        "request":     request,
        "repo":        repo,
        "archive":     archive,
        "path":        cur,
        "breadcrumbs": _crumbs(cur),
        "dirs":        dirs,
        "files":       files,
        "parent_path": parent_path,
        "error":       None,
        "total":       len(entries),
    })


@router.get("/{repo_id}/{archive}/download")
def browser_download(repo_id: int, archive: str, path: str):
    """Streamt eine Datei via borg extract --stdout direkt an den Browser."""
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("Repo nicht gefunden.", 404)

    clean = path.lstrip("/").replace("..", "").strip()
    if not clean:
        return HTMLResponse("Ungültiger Pfad.", 400)

    env      = _env(repo_id)
    filename = PurePosixPath(clean).name

    def _stream():
        proc = subprocess.Popen(
            [BORG, "extract", "--stdout", f"{repo['path']}::{archive}", clean],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env
        )
        try:
            while chunk := proc.stdout.read(65536):
                yield chunk
        finally:
            proc.stdout.close()
            proc.wait()

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
