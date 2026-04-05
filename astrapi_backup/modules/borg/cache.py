# modules/borg/cache.py
"""
Befüllt den lokalen Archiv-Cache im Hintergrund nach einem erfolgreichen Backup.
Wird von jobs.py am Ende von run_single() aufgerufen.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from astrapi.core.system.logger import log

# Pro item_id ein Lock – verhindert parallele Cache-Rebuilds für denselben Job
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

# Felder die tatsächlich für Anzeige und Download gebraucht werden
_NEEDED_FIELDS = {"path", "type", "size", "mtime", "mode"}

# Maximale Anzahl paralleler borg-SSH-Aufrufe pro Cache-Rebuild
_MAX_WORKERS = 4


def _get_lock(item_id: str) -> threading.Lock:
    with _locks_guard:
        if item_id not in _locks:
            _locks[item_id] = threading.Lock()
        return _locks[item_id]


def update(item_id: str, entry: dict) -> None:
    """Aktualisiert den Cache synchron (blockiert bis fertig).

    Läuft bereits ein Update für diese item_id, wird gewartet bis es abgeschlossen ist.
    Wird von jobs.py nach einem Backup aufgerufen.
    """
    item_id = str(item_id)
    lock = _get_lock(item_id)
    lock.acquire()
    _run(item_id, entry, lock)  # _run gibt das Lock immer im finally-Block frei


def update_async(item_id: str, entry: dict) -> None:
    """Startet die Cache-Aktualisierung in einem Daemon-Thread (nicht-blockierend).

    Läuft bereits ein Update für diese item_id, wird der Aufruf übersprungen.
    Wird vom API-Refresh-Endpunkt verwendet.
    """
    item_id = str(item_id)
    lock = _get_lock(item_id)
    if not lock.acquire(blocking=False):
        log("INFO", f"[cache] Update für Job {item_id} läuft bereits, übersprungen")
        return
    t = threading.Thread(target=_run, args=(item_id, entry, lock), daemon=True)
    t.start()


def _run(item_id: str, entry: dict, lock: threading.Lock) -> None:
    try:
        from astrapi_backup.modules.borg.storage import (
            get_cached_archive_names,
            delete_file_cache_for_archives,
            save_archive_cache_incremental,
            save_stats_cache,
        )
        from astrapi_backup.modules.borg.api import _get_target_info, _list_archives, _load_archive_entries, _repo_info
        from astrapi_backup.modules.borg.utils import borg_env as _borg_env

        env        = _borg_env()
        connection, repo = _get_target_info(entry)

        archives, error = _list_archives(repo, env, connection)
        if error or not archives:
            log("WARNING", f"[cache] Archivliste nicht abrufbar: {error}")
            return

        live_names   = {a["name"] for a in archives}
        cached_names = get_cached_archive_names(item_id)

        # Veraltete Archive aus dem Cache entfernen
        stale = cached_names - live_names
        if stale:
            delete_file_cache_for_archives(item_id, stale)
            log("INFO", f"[cache] {len(stale)} veraltete Archive entfernt")

        # Nur neue Archive laden
        to_load = [a for a in archives if a["name"] not in cached_names]
        if not to_load:
            log("INFO", f"[cache] Alle {len(archives)} Archive bereits gecacht, nichts zu tun")
            # Archivliste trotzdem aktualisieren (cached_at)
            save_archive_cache_incremental(item_id, archives, {})
        else:
            log("INFO", f"[cache] {len(to_load)} neue Archive laden ({len(archives) - len(to_load)} bereits gecacht)")

            def _load_one(archive_name: str) -> tuple[str, list]:
                entries = _load_archive_entries(repo, archive_name, env, timeout=600, connection=connection)
                slim = [{k: e[k] for k in _NEEDED_FIELDS if k in e} for e in entries]
                log("INFO", f"[cache] {archive_name}: {len(slim)} Einträge gecacht")
                return archive_name, slim

            file_map: dict = {}
            with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(to_load))) as pool:
                futures = {pool.submit(_load_one, a["name"]): a["name"] for a in to_load}
                for future in as_completed(futures):
                    try:
                        name, entries = future.result()
                        file_map[name] = entries
                    except Exception as e:
                        archive_name = futures[future]
                        log("WARNING", f"[cache] Fehler beim Laden von {archive_name}: {e}")

            save_archive_cache_incremental(item_id, archives, file_map)

        info, _ = _repo_info(repo, env, connection)
        if info:
            save_stats_cache(item_id, info)
            log("INFO", f"[cache] Statistiken für Job {item_id} gecacht")

        log("INFO", f"[cache] Cache für Job {item_id} fertig ({len(archives)} Archive, {len(to_load)} neu geladen)")
    except Exception as e:
        log("WARNING", f"[cache] Fehler beim Cache-Update: {e}")
    finally:
        lock.release()
