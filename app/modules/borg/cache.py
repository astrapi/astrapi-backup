# modules/borg/cache.py
"""
Befüllt den lokalen Archiv-Cache im Hintergrund nach einem erfolgreichen Backup.
Wird von jobs.py am Ende von run_single() aufgerufen.
"""
import threading
from helpers.logger import log

# Pro item_id ein Lock – verhindert parallele Cache-Rebuilds für denselben Job
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_lock(item_id: str) -> threading.Lock:
    with _locks_guard:
        if item_id not in _locks:
            _locks[item_id] = threading.Lock()
        return _locks[item_id]


def update(item_id: str, entry: dict) -> None:
    """Startet die Cache-Aktualisierung in einem Daemon-Thread.

    Läuft bereits ein Update für diese item_id, wird der Aufruf übersprungen.
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
        from api.storage import save_archive_cache, save_stats_cache
        from modules.borg.api import _repo_path, _borg_env, _list_archives, _load_archive_entries, _repo_info

        env  = _borg_env()
        repo = _repo_path(entry)

        archives, error = _list_archives(repo, env)
        if error or not archives:
            log("WARNING", f"[cache] Archivliste nicht abrufbar: {error}")
            return

        file_map: dict = {}
        for a in archives:
            entries = _load_archive_entries(repo, a["name"], env, timeout=600)
            file_map[a["name"]] = entries
            log("INFO", f"[cache] {a['name']}: {len(entries)} Einträge gecacht")

        save_archive_cache(item_id, archives, file_map)

        info, _ = _repo_info(repo, env)
        if info:
            save_stats_cache(item_id, info)
            log("INFO", f"[cache] Statistiken für Job {item_id} gecacht")

        log("INFO", f"[cache] Cache für Job {item_id} fertig ({len(archives)} Archive)")
    except Exception as e:
        log("WARNING", f"[cache] Fehler beim Cache-Update: {e}")
    finally:
        lock.release()
