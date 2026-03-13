# modules/borg/cache.py
"""
Befüllt den lokalen Archiv-Cache im Hintergrund nach einem erfolgreichen Backup.
Wird von jobs.py am Ende von run_single() aufgerufen.
"""
import threading
from helpers.logger import log


def update(item_id: str, entry: dict) -> None:
    """Startet die Cache-Aktualisierung in einem Daemon-Thread."""
    t = threading.Thread(target=_run, args=(str(item_id), entry), daemon=True)
    t.start()


def _run(item_id: str, entry: dict) -> None:
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
