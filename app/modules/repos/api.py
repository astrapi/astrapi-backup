# api/routers/repos.py
# Verwaltung lokaler Borg-Repositories (CRUD, borg init, borg info)

import os
import subprocess
import json
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

from api.templates import templates
from api.storage import list_repos, get_repo, create_repo, update_repo, delete_repo
from helpers.secrets import get_secret_safe, set_secret

router = APIRouter(tags=["repos"])

BORG = "/var/lib/backupadm/.venv/bin/borg"


def _borg_env(repo_id: int) -> dict:
    env = dict(os.environ)
    # Erst repo-spezifische Passphrase, Fallback auf globale
    passphrase = (
        get_secret_safe(f"BORG_PASSPHRASE_{repo_id}")
        or get_secret_safe("BORG_PASSPHRASE", "")
    )
    env["BORG_PASSPHRASE"] = passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env


def _borg_info(path: str, env: dict) -> dict:
    """Ruft borg info --json ab und gibt ein Dict zurück."""
    try:
        result = subprocess.run(
            [BORG, "info", "--json", path],
            capture_output=True, text=True, timeout=60, env=env
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _borg_list(path: str, env: dict) -> list:
    """Ruft borg list --json ab – gibt Liste der Archive zurück."""
    try:
        result = subprocess.run(
            [BORG, "list", "--json", path],
            capture_output=True, text=True, timeout=60, env=env
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            archives = data.get("archives", [])
            # Neueste zuerst
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


# ── Repo-Liste (HTMX-Partial) ─────────────────────────────────────────────────

@router.get("/tab", response_class=HTMLResponse)
def repos_tab(request: Request):
    repos = list_repos()
    # Für jedes Repo: kurze Statistik via borg info
    for repo in repos:
        env = _borg_env(repo["id"])
        info = _borg_info(repo["path"], env)
        cache = info.get("cache", {}).get("stats", {})
        repo["total_size"]    = _fmt_size(cache.get("total_size", 0))
        repo["total_csize"]   = _fmt_size(cache.get("total_csize", 0))
        repo["num_archives"]  = cache.get("total_chunks", None)
        # Archiv-Anzahl via list
        archives = _borg_list(repo["path"], env)
        repo["archive_count"] = len(archives)
        repo["last_archive"]  = archives[0]["time"][:16].replace("T", " ") if archives else "—"
        repo["reachable"]     = bool(info)
    return templates.TemplateResponse("repos/partials/tab.html", {
        "request": request,
        "repos": repos,
    })


@router.get("/list", response_class=HTMLResponse)
def repos_list(request: Request):
    return repos_tab(request)


# ── Einzelnes Repo: Info ──────────────────────────────────────────────────────

@router.get("/{repo_id}/info", response_class=HTMLResponse)
def repo_info(request: Request, repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", status_code=404)
    env = _borg_env(repo_id)
    info = _borg_info(repo["path"], env)
    archives = _borg_list(repo["path"], env)
    # Deduplizierungsrate berechnen
    cache = info.get("cache", {}).get("stats", {})
    orig  = cache.get("total_size", 0)
    dedup = cache.get("unique_size", 0)
    ratio = f"{(1 - dedup/orig)*100:.1f}%" if orig > 0 else "—"
    return templates.TemplateResponse("repos/partials/info_modal.html", {
        "request":    request,
        "repo":       repo,
        "info":       info,
        "archives":   archives[:20],
        "cache":      cache,
        "orig_size":  _fmt_size(orig),
        "dedup_size": _fmt_size(dedup),
        "dedup_ratio": ratio,
        "archive_count": len(archives),
    })


# ── Neu anlegen Modal ─────────────────────────────────────────────────────────

@router.get("/create-modal", response_class=HTMLResponse)
def repo_create_modal(request: Request):
    from core.ui.settings_registry import get_module
    from helpers.secrets import get_secret_safe
    return templates.TemplateResponse("repos/partials/create_modal.html", {
        "request":              request,
        "base_path":            get_module("repos", "base_path", ""),
        "global_passphrase_set": bool(get_secret_safe("BORG_PASSPHRASE")),
        "mode":                 "init",
        "errors":               [],
        "values":               None,
    })


# ── Repo anlegen: borg init ───────────────────────────────────────────────────

@router.post("/create", response_class=HTMLResponse)
async def repo_create(
    request: Request,
    action:      str = Form("init"),
    name:        str = Form(...),
    path:        str = Form(...),
    description: str = Form(""),
    encryption:  str = Form("repokey-blake2"),
    passphrase:  str = Form(""),
):
    from core.ui.settings_registry import get_module
    from api.storage import get_repo_by_path
    from helpers.secrets import get_secret_safe

    base_path = get_module("repos", "base_path", "")
    global_passphrase_set = bool(get_secret_safe("BORG_PASSPHRASE"))

    def _err(errors):
        return templates.TemplateResponse("repos/partials/create_modal.html", {
            "request":              request,
            "errors":               errors,
            "values":               {"name": name, "path": path, "description": description,
                                     "encryption": encryption},
            "mode":                 action,
            "base_path":            base_path,
            "global_passphrase_set": global_passphrase_set,
        })

    errors = []
    if not name.strip():
        errors.append("Name ist erforderlich.")
    if not path.strip():
        errors.append("Pfad ist erforderlich.")
    if get_repo_by_path(path.strip()):
        errors.append("Dieser Pfad ist bereits registriert.")
    if errors:
        return _err(errors)

    # Passphrase: repo-spezifisch oder leer (→ globale wird verwendet)
    effective_passphrase = passphrase or get_secret_safe("BORG_PASSPHRASE", "")
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = effective_passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

    if action == "init":
        # Verzeichnis anlegen
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return _err([f"Verzeichnis konnte nicht angelegt werden: {e}"])

        env["BORG_NEW_PASSPHRASE"] = effective_passphrase
        try:
            result = subprocess.run(
                [BORG, "init", "--encryption", encryption, path],
                capture_output=True, text=True, timeout=60, env=env
            )
            if result.returncode not in (0, 1):
                return _err([f"borg init fehlgeschlagen: {result.stderr.strip()}"])
        except Exception as e:
            return _err([f"borg init Fehler: {e}"])

    else:  # import
        # Pfad muss existieren
        if not Path(path.strip()).exists():
            return _err([f"Pfad existiert nicht: {path}"])
        # Kurzer Verbindungstest via borg info
        try:
            result = subprocess.run(
                [BORG, "info", path.strip()],
                capture_output=True, text=True, timeout=60, env=env
            )
            if result.returncode not in (0, 1):
                return _err([f"Repository konnte nicht gelesen werden: {result.stderr.strip()}"])
        except Exception as e:
            return _err([f"borg info Fehler: {e}"])
        # Encryption aus dem Repo auslesen
        try:
            info = json.loads(subprocess.run(
                [BORG, "info", "--json", path.strip()],
                capture_output=True, text=True, timeout=60, env=env
            ).stdout or "{}")
            enc = info.get("encryption", {}).get("mode", encryption)
            if enc:
                encryption = enc
        except Exception:
            pass

    repo_id = create_repo(name.strip(), path.strip(), description.strip(), encryption)

    # Repo-spezifische Passphrase nur speichern wenn explizit angegeben
    if passphrase:
        set_secret(f"BORG_PASSPHRASE_{repo_id}", passphrase)

    return repos_tab(request)


# ── Repo bearbeiten Modal ─────────────────────────────────────────────────────

@router.get("/{repo_id}/edit-modal", response_class=HTMLResponse)
def repo_edit_modal(request: Request, repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", status_code=404)
    has_passphrase = bool(get_secret_safe(f"BORG_PASSPHRASE_{repo_id}"))
    return templates.TemplateResponse("repos/partials/edit_modal.html", {
        "request": request,
        "repo": repo,
        "has_passphrase": has_passphrase,
    })


@router.post("/{repo_id}/edit", response_class=HTMLResponse)
async def repo_edit(
    request: Request,
    repo_id:     int,
    name:        str = Form(...),
    path:        str = Form(...),
    description: str = Form(""),
    passphrase:  str = Form(""),
):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", status_code=404)
    update_repo(repo_id, name.strip(), path.strip(), description.strip())
    if passphrase:
        set_secret(f"BORG_PASSPHRASE_{repo_id}", passphrase)
    return repos_tab(request)


# ── Repo löschen (nur DB-Eintrag, kein borg delete) ──────────────────────────

@router.get("/{repo_id}/delete-modal", response_class=HTMLResponse)
def repo_delete_modal(request: Request, repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return HTMLResponse("<p>Repo nicht gefunden.</p>", status_code=404)
    return templates.TemplateResponse("repos/partials/delete_modal.html", {
        "request": request,
        "repo": repo,
    })


@router.delete("/{repo_id}", response_class=HTMLResponse)
def repo_delete(request: Request, repo_id: int):
    delete_repo(repo_id)
    return repos_tab(request)


# ── Passphrase testen ─────────────────────────────────────────────────────────

@router.post("/{repo_id}/test", response_class=JSONResponse)
async def repo_test(repo_id: int):
    repo = get_repo(repo_id)
    if not repo:
        return JSONResponse({"ok": False, "msg": "Repo nicht gefunden."})
    env = _borg_env(repo_id)
    info = _borg_info(repo["path"], env)
    if info:
        return JSONResponse({"ok": True, "msg": "Verbindung erfolgreich."})
    return JSONResponse({"ok": False, "msg": "Repo nicht erreichbar oder Passphrase falsch."})


# ── Modul-Einstellungen ───────────────────────────────────────────────────────

@router.post("/settings/base-path", response_class=HTMLResponse)
async def save_base_path(request: Request, repos_base_path: str = Form("")):
    from core.ui.settings_registry import set_module
    set_module("repos", "base_path", repos_base_path.strip())
    return HTMLResponse('<span style="color:var(--g);">✔ Gespeichert</span>')


@router.post("/settings/passphrase", response_class=HTMLResponse)
async def save_borg_passphrase(request: Request):
    form = await request.form()
    val  = form.get("borg_passphrase", "").strip()
    if val:
        set_secret("BORG_PASSPHRASE", val)
    return HTMLResponse('<span style="color:var(--g);">✔ Gespeichert</span>')
