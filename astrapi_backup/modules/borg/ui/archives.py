# modules/borg/api.py
import json
import shlex
import subprocess
import threading
from pathlib import PurePosixPath
from urllib.parse import quote as _urlquote

from astrapi_core.system.cmd import build_connection_string, is_local
from astrapi_core.system.logger import log
from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from astrapi_backup.api.storage import get_item
from astrapi_backup.api.templates import templates
from astrapi_backup.modules.borg.cache.storage import (
    archive_is_cached,
    get_archive_cache,
    get_file_cache,
    get_stats_cache,
    save_archive_list_cache,
    save_file_cache_for_archive,
    save_stats_cache,
)
from astrapi_backup.modules.borg.jobs import _get_host_info as _job_get_host_info
from astrapi_backup.modules.borg.utils import borg_bin as _borg_bin
from astrapi_backup.modules.borg.utils import borg_env as _borg_env

from .crud import api_router as router

KEY = "borg"

# Verhindert parallele save_file_cache_for_archive-Threads für dieselbe (item_id, archive)-Kombination
_file_cache_building: set[tuple[str, str]] = set()
_file_cache_building_lock = threading.Lock()


def _get_target_info(entry: dict) -> tuple[str, str]:
    """Gibt (ssh_connection, lokaler_repo_pfad) zurück für Borg-Befehle auf dem Ziel-Host."""
    try:
        target_host, target_ssh_user, _ = _job_get_host_info(entry, "target")
    except ValueError:
        target_host = None
        target_ssh_user = None
    target_path = entry.get("target_path", "")
    if not target_host or is_local(target_host):
        return "local", target_path
    return build_connection_string(target_host, target_ssh_user), target_path


def _repo_path(entry: dict) -> str:
    """Repo-Pfad für Anzeige."""
    _, path = _get_target_info(entry)
    return path


def _borg_cmd_str(cmd_args: list, env: dict) -> str:
    """Baut einen sicheren Shell-Befehl mit gequoteten Argumenten."""
    passphrase = env.get("BORG_PASSPHRASE", "")
    parts = [f"BORG_PASSPHRASE={shlex.quote(passphrase)}", shlex.quote(_borg_bin())]
    parts += [shlex.quote(a) for a in cmd_args]
    return " ".join(parts)


def _borg_run(
    cmd_args: list, connection: str, env: dict, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Führt einen Borg-Befehl auf dem Ziel-Host aus (lokal oder per SSH)."""
    cmd_str = _borg_cmd_str(cmd_args, env)
    if connection == "local":
        return subprocess.run(
            ["bash", "-c", cmd_str], capture_output=True, text=True, timeout=timeout, env=env
        )
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", connection, cmd_str],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _borg_popen(cmd_args: list, connection: str, env: dict) -> subprocess.Popen:
    """Öffnet einen Borg-Prozess auf dem Ziel-Host (für Streaming)."""
    cmd_str = _borg_cmd_str(cmd_args, env)
    if connection == "local":
        return subprocess.Popen(
            ["bash", "-c", cmd_str], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env
        )
    return subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", connection, cmd_str],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _list_archives(repo_path: str, env: dict, connection: str = "local") -> tuple[list, str | None]:
    try:
        r = _borg_run(["list", "--json", repo_path], connection, env)
        if r.returncode == 0:
            archives = json.loads(r.stdout).get("archives", [])
            archives.sort(key=lambda a: a.get("time", ""), reverse=True)
            return archives, None
        return [], r.stderr.strip()
    except Exception as e:
        return [], str(e)


def _load_archive_entries(
    repo_path: str, archive: str, env: dict, timeout: int = 60, connection: str = "local"
) -> list[dict]:
    try:
        r = _borg_run(["list", "--json-lines", f"{repo_path}::{archive}"], connection, env, timeout)
        if r.returncode != 0:
            log(
                "WARNING",
                f"[borg] list --json-lines fehlgeschlagen (rc={r.returncode}): {r.stderr.strip()[:300]}",
            )
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
    except subprocess.TimeoutExpired:
        log(
            "WARNING",
            f"[borg] list --json-lines Timeout nach {timeout}s für {repo_path}::{archive}",
        )
        return []
    except Exception as e:
        log("WARNING", f"[borg] list --json-lines Exception: {e}")
        return []


from astrapi_core.system.format import fmt_bytes as _fmt_size


def _sanitize_path(path: str) -> str:
    """Bereinigt einen Archiv-Pfad und verwirft '..' Komponenten hart."""
    clean = path.lstrip("/").strip()
    if not clean:
        raise HTTPException(400, "Ungültiger Pfad")
    if any(part == ".." for part in PurePosixPath(clean).parts):
        raise HTTPException(400, "Ungültiger Pfad")
    return clean


def _validate_path_in_cache(item_id: str, archive: str, path: str) -> None:
    """Prüft ob ein Dateipfad im Cache bekannt ist. Kein Cache → 404."""
    cached = get_file_cache(item_id, archive)
    if not cached:
        raise HTTPException(
            404, "Kein Datei-Cache vorhanden. Bitte zuerst Archiv im Browser öffnen."
        )
    known = {e["path"].lstrip("/") for e in cached}
    if path not in known:
        raise HTTPException(404, f"Pfad nicht im Archiv gefunden: {path}")


def _repo_info(
    repo_path: str, env: dict, connection: str = "local"
) -> tuple[dict | None, str | None]:
    """Ruft borg info --json für ein Repo auf und gibt das geparste Dict zurück."""
    try:
        r = _borg_run(["info", "--json", repo_path], connection, env)
        if r.returncode == 0:
            return json.loads(r.stdout), None
        return None, r.stderr.strip()
    except Exception as e:
        return None, str(e)


def _dir_view(entries: list[dict], cur: str) -> tuple[list, list]:
    dirs_seen: set = set()
    dirs: list = []
    files: list = []
    for entry in entries:
        p = entry.get("path", "").lstrip("/")
        if not p or p == ".":
            continue
        if cur:
            if not p.startswith(cur + "/"):
                continue
            rest = p[len(cur) + 1 :]
        else:
            rest = p
        if not rest:
            continue
        parts = rest.split("/")
        child = parts[0]
        full = (cur + "/" + child).lstrip("/")
        is_dir = entry.get("type") in ("d", "D") or len(parts) > 1
        if len(parts) > 1:
            if full not in dirs_seen:
                dirs_seen.add(full)
                dirs.append({"name": child, "path": full, "mtime": ""})
        else:
            if is_dir:
                if full not in dirs_seen:
                    dirs_seen.add(full)
                    dirs.append(
                        {
                            "name": child,
                            "path": full,
                            "mtime": entry.get("mtime", "")[:16].replace("T", " "),
                        }
                    )
            else:
                files.append(
                    {
                        "name": child,
                        "path": p,
                        "size_fmt": _fmt_size(entry.get("size", 0)),
                        "mtime": entry.get("mtime", "")[:16].replace("T", " "),
                        "mode": entry.get("mode", ""),
                    }
                )
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    return dirs, files


# ── Archiv-Browser ────────────────────────────────────────────────────────────


@router.get("/{item_id}/archives", response_class=HTMLResponse)
def archives_modal(item_id: str, request: Request):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    archives, cached_at = get_archive_cache(item_id)
    error = (
        None
        if archives
        else (
            "Noch kein Cache vorhanden. Bitte zuerst ein Backup ausführen."
            if not cached_at
            else "Cache ist leer."
        )
    )
    return templates.TemplateResponse(
        request,
        "borg/dialogs/archives/modal.html",
        {
            "item_id": item_id,
            "description": entry.get("description", item_id),
            "repo_path": _repo_path(entry),
            "archives": archives,
            "cached_at": cached_at,
            "error": error,
        },
    )


@router.get("/{item_id}/archives/list", response_class=HTMLResponse)
def archives_list(item_id: str, request: Request):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    archives, cached_at = get_archive_cache(item_id)
    return templates.TemplateResponse(
        request,
        "borg/dialogs/archives/list.html",
        {
            "item_id": item_id,
            "archives": archives,
            "cached_at": cached_at,
            "error": None if archives else "Noch kein Cache vorhanden.",
        },
    )


@router.post("/{item_id}/archives/refresh", response_class=HTMLResponse)
def refresh_archives(item_id: str, request: Request):
    """Aktualisiert die Archivliste live und speichert sie im Cache."""
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    env = _borg_env()
    connection, repo = _get_target_info(entry)
    archives, live_error = _list_archives(repo, env, connection)
    if not live_error and archives:
        cached_at = save_archive_list_cache(item_id, archives)
        error = None
        # Datei-Cache aller Archive im Hintergrund aufbauen
        from astrapi_backup.modules.borg import cache as _borg_cache

        _borg_cache.update_async(item_id, entry)
    else:
        archives, cached_at = get_archive_cache(item_id)
        error = live_error
    return templates.TemplateResponse(
        request,
        "borg/dialogs/archives/list.html",
        {
            "item_id": item_id,
            "archives": archives,
            "cached_at": cached_at,
            "error": error,
        },
    )


@router.get("/{item_id}/archives/{archive}/browse", response_class=HTMLResponse)
def browse_archive(item_id: str, archive: str, request: Request, path: str = ""):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    cur = path.strip("/")
    # Cache-first: Fallback nur wenn Archiv NICHT im Cache registriert ist
    try:
        entries = get_file_cache(item_id, archive)
        cached = archive_is_cached(item_id, archive) if not entries else True
    except Exception:
        entries = []
        cached = False
    if not entries and not cached:
        env = _borg_env()
        connection, repo = _get_target_info(entry)
        entries = _load_archive_entries(repo, archive, env, connection=connection)
        if entries:
            key = (item_id, archive)
            with _file_cache_building_lock:
                already = key in _file_cache_building
                if not already:
                    _file_cache_building.add(key)
            if not already:

                def _save_and_release(iid, arc, ents):
                    try:
                        save_file_cache_for_archive(iid, arc, ents)
                    finally:
                        with _file_cache_building_lock:
                            _file_cache_building.discard((iid, arc))

                threading.Thread(
                    target=_save_and_release,
                    args=(item_id, archive, entries),
                    daemon=True,
                ).start()
    dirs, files = _dir_view(entries, cur)
    crumbs = [{"label": "Wurzel", "path": ""}]
    acc = ""
    for part in PurePosixPath(cur).parts if cur else []:
        acc = (acc + "/" + part).lstrip("/")
        crumbs.append({"label": part, "path": acc})
    parent_path = None
    if cur:
        p = str(PurePosixPath(cur).parent)
        parent_path = "" if p == "." else p
    return templates.TemplateResponse(
        request,
        "borg/dialogs/archives/browse.html",
        {
            "item_id": item_id,
            "archive": archive,
            "path": cur,
            "breadcrumbs": crumbs,
            "dirs": dirs,
            "files": files,
            "parent_path": parent_path,
            "error": None
            if (entries or cached)
            else "Archiv nicht im Cache und Server nicht erreichbar.",
            "total": len(entries),
        },
    )


@router.get("/{item_id}/archives/{archive}/download")
def download_archive_file(item_id: str, archive: str, path: str):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    clean = _sanitize_path(path)
    _validate_path_in_cache(item_id, archive, clean)
    env = _borg_env()
    connection, repo = _get_target_info(entry)
    filename = PurePosixPath(clean).name

    def _stream():
        proc = _borg_popen(["extract", "--stdout", f"{repo}::{archive}", clean], connection, env)
        try:
            while chunk := proc.stdout.read(65536):
                yield chunk
        finally:
            proc.stdout.close()
            rc = proc.wait()
            if rc != 0:
                stderr = proc.stderr.read().decode(errors="replace").strip()
                log("WARNING", f"[download] borg extract rc={rc}: {stderr}")

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_urlquote(filename)}"},
    )


@router.get("/{item_id}/archives/{archive}/download-bundle")
def download_bundle(item_id: str, archive: str, path: list[str] = Query(default=[])):
    """Mehrere Dateien oder ein Verzeichnis als tar-Stream.

    Einzelne Dateien: ?path=dir/file1&path=dir/file2
    Verzeichnis:      ?path=subdir/   (mit abschließendem Slash)
    Alles:            kein path-Parameter
    """
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    env = _borg_env()
    connection, repo = _get_target_info(entry)

    clean = []
    for p in path:
        if not p.strip():
            continue
        if p.endswith("/"):
            # Verzeichnispfad: keine Cache-Validierung (Cache enthält keine Dirs)
            sanitized = _sanitize_path(p.rstrip("/")) + "/"
        else:
            sanitized = _sanitize_path(p)
            _validate_path_in_cache(item_id, archive, sanitized)
        clean.append(sanitized)

    if len(clean) == 1 and clean[0].endswith("/"):
        label = PurePosixPath(clean[0].rstrip("/")).name or "root"
        filename = f"{archive}_{label}.tar"
    elif len(clean) == 1:
        filename = PurePosixPath(clean[0]).name + ".tar"
    elif clean:
        filename = f"{archive}_selection.tar"
    else:
        filename = f"{archive}.tar"

    def _stream():
        proc = _borg_popen(["extract", "--stdout", f"{repo}::{archive}", *clean], connection, env)
        try:
            while chunk := proc.stdout.read(65536):
                yield chunk
        finally:
            proc.stdout.close()
            proc.wait()

    return StreamingResponse(
        _stream(),
        media_type="application/x-tar",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_urlquote(filename)}"},
    )


# ── Repo-Statistiken ─────────────────────────────────────────────────────────


def _build_stats(info: dict) -> dict | None:
    try:
        cs = (info.get("cache") or {}).get("stats") or {}
        archives = info.get("archives") or []
        repo = info.get("repository") or {}
        archives_sorted = sorted(archives, key=lambda a: a.get("time", ""), reverse=True)
        total_size = cs.get("total_size", 0) or 0
        total_csize = cs.get("total_csize", 0) or 0
        unique_size = cs.get("unique_size", 0) or 0
        unique_csize = cs.get("unique_csize", 0) or 0
        comp_ratio = round((1 - total_csize / total_size) * 100, 1) if total_size > 0 else 0.0
        dedup_eff = round((1 - unique_csize / total_csize) * 100, 1) if total_csize > 0 else 0.0
        return {
            "total_size_fmt": _fmt_size(total_size),
            "total_csize_fmt": _fmt_size(total_csize),
            "unique_size_fmt": _fmt_size(unique_size),
            "unique_csize_fmt": _fmt_size(unique_csize),
            "comp_ratio": comp_ratio,
            "dedup_efficiency": dedup_eff,
            "total_chunks": cs.get("total_chunks", 0) or 0,
            "unique_chunks": cs.get("total_unique_chunks", 0) or 0,
            "num_archives": len(archives),
            "newest_archive": archives_sorted[0].get("time", "")[:16].replace("T", " ")
            if archives_sorted
            else "–",
            "oldest_archive": archives_sorted[-1].get("time", "")[:16].replace("T", " ")
            if archives_sorted
            else "–",
            "last_modified": repo.get("last_modified", "")[:16].replace("T", " "),
        }
    except Exception as e:
        log("WARNING", f"[stats] _build_stats Fehler: {e}")
        return None


def _enrich_stats_from_archive_cache(stats: dict, item_id: str) -> dict:
    """Ergänzt num_archives/newest/oldest aus borg_archive_cache falls borg info sie nicht liefert."""
    if stats.get("num_archives", 0) == 0:
        archives, _ = get_archive_cache(item_id)
        if archives:
            stats = dict(stats)
            stats["num_archives"] = len(archives)
            stats["newest_archive"] = archives[0].get("time", "")[:16].replace("T", " ")
            stats["oldest_archive"] = archives[-1].get("time", "")[:16].replace("T", " ")
    return stats


@router.get("/{item_id}/stats", response_class=HTMLResponse)
def stats_modal(item_id: str, request: Request):
    """Zeigt Repository-Statistiken aus dem Cache."""
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    info, cached_at = get_stats_cache(item_id)
    stats = _build_stats(info) if info else None
    if stats:
        stats = _enrich_stats_from_archive_cache(stats, item_id)
    return templates.TemplateResponse(
        request,
        "borg/dialogs/stats/modal.html",
        {
            "item_id": item_id,
            "description": entry.get("description", item_id),
            "repo_path": _repo_path(entry),
            "stats": stats,
            "cached_at": cached_at,
            "error": None
            if stats
            else "Noch kein Cache vorhanden. Bitte zuerst ein Backup ausführen.",
        },
    )


@router.post("/{item_id}/stats/refresh", response_class=HTMLResponse)
def refresh_stats(item_id: str, request: Request):
    """Aktualisiert Statistiken live und speichert sie im Cache."""
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    env = _borg_env()
    connection, repo = _get_target_info(entry)
    info, live_error = _repo_info(repo, env, connection)
    if info:
        cached_at = save_stats_cache(item_id, info)
        error = None
    else:
        info, cached_at = get_stats_cache(item_id)
        error = live_error
    stats = _build_stats(info) if info else None
    if stats:
        stats = _enrich_stats_from_archive_cache(stats, item_id)
    return templates.TemplateResponse(
        request,
        "borg/dialogs/stats/content.html",
        {
            "item_id": item_id,
            "stats": stats,
            "cached_at": cached_at,
            "error": error if error else (None if stats else "Keine Statistiken verfügbar."),
        },
    )
