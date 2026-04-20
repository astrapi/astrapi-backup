# app/modules/borg/storage.py
"""Borg-spezifischer SQLite-Cache für Archive, Dateien und Repo-Statistiken."""
import json
from datetime import datetime

from astrapi_core.system.db import _conn


# ── Archive-Cache ─────────────────────────────────────────────────────────────

_ARCHIVE_CACHE_DDL = """
    CREATE TABLE IF NOT EXISTS borg_archive_cache (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id   TEXT NOT NULL,
        name      TEXT NOT NULL,
        time      TEXT NOT NULL,
        cached_at TEXT NOT NULL
    )
"""

_FILE_CACHE_DDL = """
    CREATE TABLE IF NOT EXISTS borg_file_cache (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        archive TEXT NOT NULL,
        path    TEXT NOT NULL,
        type    TEXT,
        size    INTEGER DEFAULT 0,
        mtime   TEXT,
        mode    TEXT
    )
"""


def _init_archive_cache() -> None:
    con = _conn()
    con.execute(_ARCHIVE_CACHE_DDL)
    con.execute(_FILE_CACHE_DDL)
    con.execute("CREATE INDEX IF NOT EXISTS idx_arc_cache_item   ON borg_archive_cache(item_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_file_cache_lookup ON borg_file_cache(item_id, archive)")
    con.commit()


def save_archive_list_cache(item_id: str, archives: list) -> str:
    """Speichert nur die Archivliste (ohne Dateieinträge). Gibt cached_at zurück."""
    _init_archive_cache()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = _conn()
    con.execute("DELETE FROM borg_archive_cache WHERE item_id=?", (item_id,))
    con.executemany(
        "INSERT INTO borg_archive_cache (item_id, name, time, cached_at) VALUES (?,?,?,?)",
        [(item_id, a["name"], a.get("time", ""), now) for a in archives],
    )
    con.commit()
    return now


def save_archive_cache(item_id: str, archives: list, file_map: dict) -> None:
    """Speichert Archivliste + alle Dateieinträge (vollständiger Cache nach Backup)."""
    _init_archive_cache()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = _conn()
    con.execute("DELETE FROM borg_archive_cache WHERE item_id=?", (item_id,))
    con.execute("DELETE FROM borg_file_cache WHERE item_id=?", (item_id,))
    con.executemany(
        "INSERT INTO borg_archive_cache (item_id, name, time, cached_at) VALUES (?,?,?,?)",
        [(item_id, a["name"], a.get("time", ""), now) for a in archives],
    )
    for archive_name, entries in file_map.items():
        con.executemany(
            "INSERT INTO borg_file_cache (item_id, archive, path, type, size, mtime, mode) "
            "VALUES (?,?,?,?,?,?,?)",
            [(item_id, archive_name,
              e.get("path", ""), e.get("type", ""),
              e.get("size", 0), e.get("mtime", ""), e.get("mode", ""))
             for e in entries],
        )
    con.commit()


def get_cached_archive_names(item_id: str) -> set[str]:
    """Gibt die Namen aller bereits gecachten Archive zurück."""
    _init_archive_cache()
    rows = _conn().execute(
        "SELECT archive AS name FROM borg_file_cache WHERE item_id=? GROUP BY archive",
        (item_id,),
    ).fetchall()
    return {r["name"] for r in rows}


def delete_file_cache_for_archives(item_id: str, archive_names: set[str]) -> None:
    """Löscht Dateieinträge für mehrere Archive (z.B. veraltete nach Borg prune)."""
    if not archive_names:
        return
    _init_archive_cache()
    con = _conn()
    con.executemany(
        "DELETE FROM borg_file_cache WHERE item_id=? AND archive=?",
        [(item_id, name) for name in archive_names],
    )
    con.commit()


def save_archive_cache_incremental(item_id: str, archives: list, new_file_map: dict) -> None:
    """Aktualisiert Archivliste und fügt nur neue Dateieinträge ein.

    Vorhandene Einträge für bekannte Archive bleiben unangetastet.
    Veraltete Archive werden vorher über delete_file_cache_for_archives entfernt.
    """
    _init_archive_cache()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = _conn()
    con.execute("DELETE FROM borg_archive_cache WHERE item_id=?", (item_id,))
    con.executemany(
        "INSERT INTO borg_archive_cache (item_id, name, time, cached_at) VALUES (?,?,?,?)",
        [(item_id, a["name"], a.get("time", ""), now) for a in archives],
    )
    for archive_name, entries in new_file_map.items():
        con.executemany(
            "INSERT INTO borg_file_cache (item_id, archive, path, type, size, mtime, mode) "
            "VALUES (?,?,?,?,?,?,?)",
            [(item_id, archive_name,
              e.get("path", ""), e.get("type", ""),
              e.get("size", 0), e.get("mtime", ""), e.get("mode", ""))
             for e in entries],
        )
    con.commit()


def get_archive_cache(item_id: str) -> tuple:
    """Gibt (archives, cached_at) zurück. archives neueste zuerst."""
    _init_archive_cache()
    rows = _conn().execute(
        "SELECT name, time, cached_at FROM borg_archive_cache WHERE item_id=? ORDER BY time DESC",
        (item_id,),
    ).fetchall()
    if not rows:
        return [], None
    return [{"name": r["name"], "time": r["time"]} for r in rows], rows[0]["cached_at"]


def archive_is_cached(item_id: str, archive: str) -> bool:
    """True wenn das Archiv im Archive-Cache registriert ist."""
    _init_archive_cache()
    row = _conn().execute(
        "SELECT 1 FROM borg_archive_cache WHERE item_id=? AND name=?",
        (item_id, archive),
    ).fetchone()
    return row is not None


def get_file_cache(item_id: str, archive: str) -> list:
    """Gibt alle gecachten Dateieinträge für ein Archiv zurück."""
    _init_archive_cache()
    rows = _conn().execute(
        "SELECT path, type, size, mtime, mode FROM borg_file_cache WHERE item_id=? AND archive=?",
        (item_id, archive),
    ).fetchall()
    return [dict(r) for r in rows]


def save_file_cache_for_archive(item_id: str, archive: str, entries: list) -> None:
    """Speichert Dateieinträge für ein einzelnes Archiv (ersetzt ggf. vorhandene)."""
    _init_archive_cache()
    con = _conn()
    con.execute("DELETE FROM borg_file_cache WHERE item_id=? AND archive=?", (item_id, archive))
    con.executemany(
        "INSERT INTO borg_file_cache (item_id, archive, path, type, size, mtime, mode) "
        "VALUES (?,?,?,?,?,?,?)",
        [(item_id, archive,
          e.get("path", ""), e.get("type", ""),
          e.get("size", 0), e.get("mtime", ""), e.get("mode", ""))
         for e in entries],
    )
    con.commit()


# ── Stats-Cache ───────────────────────────────────────────────────────────────

_STATS_CACHE_DDL = """
    CREATE TABLE IF NOT EXISTS borg_stats_cache (
        item_id    TEXT PRIMARY KEY,
        stats_json TEXT NOT NULL,
        cached_at  TEXT NOT NULL
    )
"""


def _init_stats_cache() -> None:
    _conn().execute(_STATS_CACHE_DDL)
    _conn().commit()


def save_stats_cache(item_id: str, info: dict) -> str:
    """Speichert borg info --json Ausgabe. Gibt cached_at zurück."""
    _init_stats_cache()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _conn().execute(
        "INSERT INTO borg_stats_cache (item_id, stats_json, cached_at) VALUES (?,?,?) "
        "ON CONFLICT(item_id) DO UPDATE SET stats_json=excluded.stats_json, cached_at=excluded.cached_at",
        (item_id, json.dumps(info), now),
    )
    _conn().commit()
    return now


def get_stats_cache(item_id: str) -> tuple:
    """Gibt (info_dict, cached_at) zurück, oder (None, None) wenn kein Cache."""
    _init_stats_cache()
    row = _conn().execute(
        "SELECT stats_json, cached_at FROM borg_stats_cache WHERE item_id=?", (item_id,)
    ).fetchone()
    if not row:
        return None, None
    return json.loads(row["stats_json"]), row["cached_at"]
