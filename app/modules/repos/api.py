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


def _create_error(*errors: str) -> HTMLResponse:
    """Gibt eine Fehlerseite in #main-content aus (mit Zurück-Button)."""
    msgs = "".join(f"<li>{e}</li>" for e in errors)
    return HTMLResponse(f"""<div id="tab-repos" class="tab-content">
  <div style="background:var(--err-bg,rgba(239,68,68,.12));
              border:1px solid var(--err-bd,rgba(239,68,68,.3));
              border-radius:var(--rad); padding:14px 18px; margin-bottom:16px;
              color:var(--err,#f87171);">
    <ul style="margin:0; padding-left:18px;">{msgs}</ul>
  </div>
  <button class="btn btn-ghost btn-sm"
          hx-get="/ui/repos/content" hx-target="#main-content" hx-swap="innerHTML">
    ← Zurück zu Repositories
  </button>
</div>""")


# ── Hilfsfunktion: Liste rendern ──────────────────────────────────────────────

def _enrich_repos() -> list:
    """Lädt alle Repos aus der DB und reichert sie mit Live-Borg-Statistiken an."""
    repos = list_repos()
    for repo in repos:
        env = _borg_env(repo["id"])
        info = _borg_info(repo["path"], env)
        cache = info.get("cache", {}).get("stats", {})
        repo["total_size"]    = _fmt_size(cache.get("total_size", 0))
        repo["total_csize"]   = _fmt_size(cache.get("total_csize", 0))
        archives = _borg_list(repo["path"], env)
        repo["archive_count"] = len(archives)
        repo["last_archive"]  = archives[0]["time"][:16].replace("T", " ") if archives else "—"
        repo["reachable"]     = bool(info)
    return repos


def _repos_cfg() -> dict:
    """Gibt Repos als Standard-cfg-Dict zurück (kompatibel mit list_wrapper_inner.html)."""
    return {
        r["id"]: {**r, "description": r["name"], "enabled": r.get("reachable", True)}
        for r in _enrich_repos()
    }


def _repos_response(request: Request):
    """Gibt die Repo-Listenpartial mit aktuellen Borg-Statistiken zurück."""
    return templates.TemplateResponse("partials/list_wrapper_inner.html", {
        "request":          request,
        "cfg":              _repos_cfg(),
        "module":           "repos",
        "container_id":     "tab-repos",
        "loading_id":       "repos-loading",
        "content_template": "repos/partials/list.html",
        "footer_template":  "repos/partials/footer.html",
        "has_toggle":       False,
        "has_run_buttons":  False,
        "running":          {},
    })


@router.get("/tab", response_class=HTMLResponse)
def repos_tab(request: Request):
    return _repos_response(request)


@router.get("/list", response_class=HTMLResponse)
def repos_list(request: Request):
    return _repos_response(request)


# ── Repo anlegen: borg init ──────────────────────────────────────────────────

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
    from api.storage import get_repo_by_path
    from helpers.secrets import get_secret_safe

    if not name.strip():
        return _create_error("Name ist erforderlich.")
    if not path.strip():
        return _create_error("Pfad ist erforderlich.")
    if get_repo_by_path(path.strip()):
        return _create_error("Dieser Pfad ist bereits registriert.")

    effective_passphrase = passphrase or get_secret_safe("BORG_PASSPHRASE", "")
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = effective_passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"

    if action == "init":
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return _create_error(f"Verzeichnis konnte nicht angelegt werden: {e}")
        env["BORG_NEW_PASSPHRASE"] = effective_passphrase
        try:
            result = subprocess.run(
                [BORG, "init", "--encryption", encryption, path],
                capture_output=True, text=True, timeout=60, env=env
            )
            if result.returncode not in (0, 1):
                return _create_error(f"borg init fehlgeschlagen: {result.stderr.strip()}")
        except Exception as e:
            return _create_error(f"borg init Fehler: {e}")
    else:  # import
        if not Path(path.strip()).exists():
            return _create_error(f"Pfad existiert nicht: {path}")
        try:
            result = subprocess.run(
                [BORG, "info", path.strip()],
                capture_output=True, text=True, timeout=60, env=env
            )
            if result.returncode not in (0, 1):
                return _create_error(f"Repository konnte nicht gelesen werden: {result.stderr.strip()}")
        except Exception as e:
            return _create_error(f"borg info Fehler: {e}")
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
    if passphrase:
        set_secret(f"BORG_PASSPHRASE_{repo_id}", passphrase)

    return _repos_response(request)



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
    return _repos_response(request)


# ── Repo löschen (nur DB-Eintrag, kein borg delete) ──────────────────────────

@router.delete("/{repo_id}", response_class=HTMLResponse)
def repo_delete(request: Request, repo_id: int):
    delete_repo(repo_id)
    return _repos_response(request)


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


