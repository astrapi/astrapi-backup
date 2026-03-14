# modules/borg/api.py
import json
import subprocess
import threading
import yaml
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, HTTPException, Request, Header, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from api.storage import (
    load_config, get_item, delete_item, save_item, next_item_id,
    get_archive_cache, save_archive_list_cache,
    get_file_cache, archive_is_cached, save_file_cache_for_archive,
    get_stats_cache, save_stats_cache,
)
from api.routers.run import get_running
from api.templates import templates
from helpers.cmd import is_local
from helpers.logger import log
from modules.borg.jobs import _borg_bin, _borg_env, preview as _preview_borg

KEY = "borg"
router = APIRouter()

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"

# Verhindert parallele save_file_cache_for_archive-Threads für dieselbe (item_id, archive)-Kombination
_file_cache_building: set[tuple[str, str]] = set()
_file_cache_building_lock = threading.Lock()


def _repo_path(entry: dict) -> str:
    """Repo-Pfad aus Server-Perspektive (direkt auf dem Backupserver)."""
    target_host = entry.get("target_host", "")
    target_path = entry.get("target_path", "")
    if is_local(target_host):
        return target_path
    return f"backupadm@{target_host}:{target_path}"


def _list_archives(repo_path: str, env: dict) -> tuple[list, str | None]:
    try:
        r = subprocess.run(
            [_borg_bin(), "list", "--json", repo_path],
            capture_output=True, text=True, timeout=60, env=env
        )
        if r.returncode == 0:
            archives = json.loads(r.stdout).get("archives", [])
            archives.sort(key=lambda a: a.get("time", ""), reverse=True)
            return archives, None
        return [], r.stderr.strip()
    except Exception as e:
        return [], str(e)


def _load_archive_entries(repo_path: str, archive: str, env: dict, timeout: int = 60) -> list[dict]:
    try:
        r = subprocess.run(
            [_borg_bin(), "list", "--json-lines", f"{repo_path}::{archive}"],
            capture_output=True, text=True, timeout=timeout, env=env
        )
        if r.returncode != 0:
            log("WARNING", f"[borg] list --json-lines fehlgeschlagen (rc={r.returncode}): {r.stderr.strip()[:300]}")
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
        log("WARNING", f"[borg] list --json-lines Timeout nach {timeout}s für {repo_path}::{archive}")
        return []
    except Exception as e:
        log("WARNING", f"[borg] list --json-lines Exception: {e}")
        return []


def _fmt_size(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


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
        raise HTTPException(404, "Kein Datei-Cache vorhanden. Bitte zuerst Archiv im Browser öffnen.")
    known = {e["path"].lstrip("/") for e in cached}
    if path not in known:
        raise HTTPException(404, f"Pfad nicht im Archiv gefunden: {path}")


def _repo_info(repo_path: str, env: dict) -> tuple[dict | None, str | None]:
    """Ruft borg info --json für ein Repo auf und gibt das geparste Dict zurück."""
    try:
        r = subprocess.run(
            [_borg_bin(), "info", "--json", repo_path],
            capture_output=True, text=True, timeout=60, env=env,
        )
        if r.returncode == 0:
            return json.loads(r.stdout), None
        return None, r.stderr.strip()
    except Exception as e:
        return None, str(e)


def _dir_view(entries: list[dict], cur: str) -> tuple[list, list]:
    dirs_seen: set = set()
    dirs:  list = []
    files: list = []
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
        parts  = rest.split("/")
        child  = parts[0]
        full   = (cur + "/" + child).lstrip("/")
        is_dir = entry.get("type") in ("d", "D") or len(parts) > 1
        if len(parts) > 1:
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
                    "size_fmt": _fmt_size(entry.get("size", 0)),
                    "mtime":    entry.get("mtime", "")[:16].replace("T", " "),
                    "mode":     entry.get("mode", ""),
                })
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    return dirs, files


def _load_schema() -> dict:
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


def _list_response(request: Request):
    return templates.TemplateResponse(
        "partials/list_wrapper_inner.html",
        {
            "request":          request,
            "cfg":              load_config(KEY),
            "module":           KEY,
            "content_template": f"{KEY}/partials/list.html",
            "container_id":     f"tab-{KEY}",
            "loading_id":       f"{KEY}-loading",
            "running":          get_running(),
        },
    )


def _clean(data: dict) -> dict:
    return {
        k: v for k, v in data.items()
        if v is not None
        and not (isinstance(v, str) and v.strip() == "")
        and not (isinstance(v, list) and len(v) == 0)
    }


def _extract_lists(schema, payload):
    """Gibt (bereinigtes payload, list_values) zurück."""
    fields = schema.get("fields", [])
    list_fields = [f["name"] for f in fields if f.get("type") == "list"]
    lists: dict = {n: [] for n in list_fields}
    for k, v in payload.items():
        for ln in list_fields:
            if k.startswith(f"{ln}_"):
                try:
                    idx = int(k[len(ln) + 1:])
                    lists[ln].append((idx, v))
                except ValueError:
                    pass
    for n in list_fields:
        lists[n] = [v for _, v in sorted(lists[n])]
    prefixes = tuple(f"{n}_" for n in list_fields)
    clean_payload = {k: v for k, v in payload.items() if not any(k.startswith(p) for p in prefixes)}
    # Fehlende Nicht-Listen-Felder auffüllen
    for f in fields:
        if f["name"] not in clean_payload and f.get("type") != "list":
            clean_payload[f["name"]] = ""
    for n in list_fields:
        clean_payload[n] = lists[n]
    return clean_payload


@router.post("/create")
async def create_one(request: Request):
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    payload = _extract_lists(_load_schema(), payload)
    save_item(KEY, next_item_id(KEY), _clean(payload))
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return payload


@router.patch("/{item_id}/edit")
async def patch_one(item_id: str, request: Request):
    iid      = int(item_id)
    existing = get_item(KEY, iid)
    if existing is None:
        raise HTTPException(404, "Item not found")
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    payload  = _extract_lists(_load_schema(), payload)
    existing.update(payload)
    save_item(KEY, iid, _clean(existing))
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return existing


@router.delete("/{item_id}/delete")
def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
    if not delete_item(KEY, item_id):
        raise HTTPException(404, "Item not found")
    if hx_request:
        return _list_response(request)


@router.post("/{item_id}/toggle")
def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
    cfg = load_config(KEY)
    cfg[item_id]["enabled"] = not cfg[item_id].get("enabled", False)
    save_item(KEY, item_id, cfg[item_id])
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "item": item_id, "enabled": cfg[item_id]["enabled"]}


@router.post("/enable-all")
def enable_all(request: Request):
    for iid, item in load_config(KEY).items():
        if not item.get("enabled", False):
            item["enabled"] = True
            save_item(KEY, iid, item)
    return _list_response(request)


@router.post("/disable-all")
def disable_all(request: Request):
    for iid, item in load_config(KEY).items():
        if item.get("enabled", True):
            item["enabled"] = False
            save_item(KEY, iid, item)
    return _list_response(request)


@router.get("/{item_id}/preview")
def preview_item(item_id: str, request: Request):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    return templates.TemplateResponse("partials/preview_modal.html", {
        "request":     request,
        "description": entry.get("description", item_id),
        "commands":    _preview_borg(item_id),
    })


# ── Archiv-Browser ────────────────────────────────────────────────────────────

@router.get("/{item_id}/archives", response_class=HTMLResponse)
def archives_modal(item_id: str, request: Request):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    archives, cached_at = get_archive_cache(item_id)
    error = None if archives else (
        "Noch kein Cache vorhanden. Bitte zuerst ein Backup ausführen."
        if not cached_at else "Cache ist leer."
    )
    return templates.TemplateResponse("borg/partials/archives_modal.html", {
        "request":     request,
        "item_id":     item_id,
        "description": entry.get("description", item_id),
        "repo_path":   _repo_path(entry),
        "archives":    archives,
        "cached_at":   cached_at,
        "error":       error,
    })


@router.get("/{item_id}/archives/list", response_class=HTMLResponse)
def archives_list(item_id: str, request: Request):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    archives, cached_at = get_archive_cache(item_id)
    return templates.TemplateResponse("borg/partials/archives_list.html", {
        "request":   request,
        "item_id":   item_id,
        "archives":  archives,
        "cached_at": cached_at,
        "error":     None if archives else "Noch kein Cache vorhanden.",
    })


@router.post("/{item_id}/archives/refresh", response_class=HTMLResponse)
def refresh_archives(item_id: str, request: Request):
    """Aktualisiert die Archivliste live und speichert sie im Cache."""
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    env  = _borg_env()
    repo = _repo_path(entry)
    archives, live_error = _list_archives(repo, env)
    if not live_error and archives:
        cached_at = save_archive_list_cache(item_id, archives)
        error = None
        # Datei-Cache aller Archive im Hintergrund aufbauen
        from modules.borg import cache as _borg_cache
        _borg_cache.update(item_id, entry)
    else:
        archives, cached_at = get_archive_cache(item_id)
        error = live_error
    return templates.TemplateResponse("borg/partials/archives_list.html", {
        "request":   request,
        "item_id":   item_id,
        "archives":  archives,
        "cached_at": cached_at,
        "error":     error,
    })


@router.get("/{item_id}/archives/{archive}/browse", response_class=HTMLResponse)
def browse_archive(item_id: str, archive: str, request: Request, path: str = ""):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    cur = path.strip("/")
    # Cache-first: Fallback nur wenn Archiv NICHT im Cache registriert ist
    try:
        entries = get_file_cache(item_id, archive)
        cached  = archive_is_cached(item_id, archive) if not entries else True
    except Exception:
        entries = []
        cached  = False
    if not entries and not cached:
        env  = _borg_env()
        repo = _repo_path(entry)
        entries = _load_archive_entries(repo, archive, env)
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
    for part in (PurePosixPath(cur).parts if cur else []):
        acc = (acc + "/" + part).lstrip("/")
        crumbs.append({"label": part, "path": acc})
    parent_path = None
    if cur:
        p = str(PurePosixPath(cur).parent)
        parent_path = "" if p == "." else p
    return templates.TemplateResponse("borg/partials/browse.html", {
        "request":     request,
        "item_id":     item_id,
        "archive":     archive,
        "path":        cur,
        "breadcrumbs": crumbs,
        "dirs":        dirs,
        "files":       files,
        "parent_path": parent_path,
        "error":       None if (entries or cached) else "Archiv nicht im Cache und Server nicht erreichbar.",
        "total":       len(entries),
    })


@router.get("/{item_id}/archives/{archive}/download")
def download_archive_file(item_id: str, archive: str, path: str):
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    clean    = _sanitize_path(path)
    _validate_path_in_cache(item_id, archive, clean)
    env      = _borg_env()
    repo     = _repo_path(entry)
    filename = PurePosixPath(clean).name

    def _stream():
        proc = subprocess.Popen(
            [_borg_bin(), "extract", "--stdout", f"{repo}::{archive}", clean],
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
    env  = _borg_env()
    repo = _repo_path(entry)

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

    cmd = [_borg_bin(), "extract", "--stdout", f"{repo}::{archive}", *clean]

    def _stream():
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env
        )
        try:
            while chunk := proc.stdout.read(65536):
                yield chunk
        finally:
            proc.stdout.close()
            proc.wait()

    return StreamingResponse(
        _stream(),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Repo-Statistiken ─────────────────────────────────────────────────────────

def _build_stats(info: dict) -> dict | None:
    try:
        cs       = (info.get("cache") or {}).get("stats") or {}
        archives = info.get("archives") or []
        repo     = info.get("repository") or {}
        archives_sorted = sorted(archives, key=lambda a: a.get("time", ""), reverse=True)
        total_size   = cs.get("total_size",  0) or 0
        total_csize  = cs.get("total_csize", 0) or 0
        unique_size  = cs.get("unique_size",  0) or 0
        unique_csize = cs.get("unique_csize", 0) or 0
        comp_ratio = round((1 - total_csize / total_size) * 100, 1) if total_size > 0 else 0.0
        dedup_eff  = round((1 - unique_csize / total_csize) * 100, 1) if total_csize > 0 else 0.0
        return {
            "total_size_fmt":   _fmt_size(total_size),
            "total_csize_fmt":  _fmt_size(total_csize),
            "unique_size_fmt":  _fmt_size(unique_size),
            "unique_csize_fmt": _fmt_size(unique_csize),
            "comp_ratio":       comp_ratio,
            "dedup_efficiency": dedup_eff,
            "total_chunks":     cs.get("total_chunks", 0) or 0,
            "unique_chunks":    cs.get("total_unique_chunks", 0) or 0,
            "num_archives":     len(archives),
            "newest_archive":   archives_sorted[0].get("time", "")[:16].replace("T", " ") if archives_sorted else "–",
            "oldest_archive":   archives_sorted[-1].get("time", "")[:16].replace("T", " ") if archives_sorted else "–",
            "last_modified":    repo.get("last_modified", "")[:16].replace("T", " "),
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
            stats["num_archives"]   = len(archives)
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
    return templates.TemplateResponse("borg/partials/stats_modal.html", {
        "request":     request,
        "item_id":     item_id,
        "description": entry.get("description", item_id),
        "repo_path":   _repo_path(entry),
        "stats":       stats,
        "cached_at":   cached_at,
        "error":       None if stats else "Noch kein Cache vorhanden. Bitte zuerst ein Backup ausführen.",
    })


@router.post("/{item_id}/stats/refresh", response_class=HTMLResponse)
def refresh_stats(item_id: str, request: Request):
    """Aktualisiert Statistiken live und speichert sie im Cache."""
    entry = get_item(KEY, item_id)
    if entry is None:
        raise HTTPException(404, "Item not found")
    env  = _borg_env()
    repo = _repo_path(entry)
    info, live_error = _repo_info(repo, env)
    if info:
        cached_at = save_stats_cache(item_id, info)
        error = None
    else:
        info, cached_at = get_stats_cache(item_id)
        error = live_error
    stats = _build_stats(info) if info else None
    if stats:
        stats = _enrich_stats_from_archive_cache(stats, item_id)
    return templates.TemplateResponse("borg/partials/stats_content.html", {
        "request":     request,
        "item_id":     item_id,
        "stats":       stats,
        "cached_at":   cached_at,
        "error":       error if error else (None if stats else "Keine Statistiken verfügbar."),
    })
