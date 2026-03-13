# api/storage.py
"""
SQLite-Backend mit einer Tabelle pro Modul, echten Spalten.
Listen (pre, post, exclude, source) werden newline-getrennt als TEXT gespeichert.

Migration: bestehende YAML-Dateien werden einmalig importiert,
danach in config/*.yaml.migrated umbenannt.
"""

import sqlite3
import threading
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH    = Path(__file__).resolve().parent.parent / "data" / "backupctl.db"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_local = threading.local()


# ── Verbindung ────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    if not getattr(_local, "conn", None):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        _local.conn = con
    return _local.conn


# ── Schema ────────────────────────────────────────────────────────

_DDL = {
    "borg": """
        CREATE TABLE IF NOT EXISTS borg (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            enabled     INTEGER NOT NULL DEFAULT 1,
            description TEXT    NOT NULL DEFAULT '',
            source_host TEXT    NOT NULL DEFAULT '',
            source_path TEXT    NOT NULL DEFAULT '',
            target_host TEXT    NOT NULL DEFAULT '',
            target_path TEXT    NOT NULL DEFAULT '',
            ssh_user    TEXT,
            pre_hooks   TEXT,
            post_hooks  TEXT,
            exclude     TEXT
        )""",

    "rsync": """
        CREATE TABLE IF NOT EXISTS rsync (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            enabled     INTEGER NOT NULL DEFAULT 1,
            description TEXT    NOT NULL DEFAULT '',
            source_host TEXT    NOT NULL DEFAULT '',
            source_path TEXT    NOT NULL DEFAULT '',
            target_host TEXT    NOT NULL DEFAULT '',
            target_path TEXT    NOT NULL DEFAULT ''
        )""",

    "proxmox_lxc": """
        CREATE TABLE IF NOT EXISTS proxmox_lxc (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vmid        INTEGER NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            node        TEXT    NOT NULL DEFAULT '',
            enabled     INTEGER NOT NULL DEFAULT 1
        )""",

    "proxmox_hosts": """
        CREATE TABLE IF NOT EXISTS proxmox_hosts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            host           TEXT    NOT NULL DEFAULT '',
            description    TEXT    NOT NULL DEFAULT '',
            enabled        INTEGER NOT NULL DEFAULT 1,
            extra_sources  TEXT
        )""",

    "proxmox_jobs": """
        CREATE TABLE IF NOT EXISTS proxmox_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job         TEXT    NOT NULL DEFAULT '',
            description TEXT    NOT NULL DEFAULT '',
            host        TEXT    NOT NULL DEFAULT '',
            type        TEXT    NOT NULL DEFAULT '',
            enabled     INTEGER NOT NULL DEFAULT 1
        )""",

    "remotes": """
        CREATE TABLE IF NOT EXISTS remotes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mac         TEXT    NOT NULL DEFAULT '',
            host        TEXT    NOT NULL DEFAULT '',
            description TEXT    NOT NULL DEFAULT '',
            ssh_user    TEXT    NOT NULL DEFAULT 'root',
            enabled     INTEGER NOT NULL DEFAULT 1
        )""",
}

# Felder die Listen sind (newline-getrennt in DB, list in Python)
_LIST_FIELDS = {
    "borg":          ["pre_hooks", "post_hooks", "exclude"],
    "proxmox_hosts": ["extra_sources"],
}


def _migrate_remotes_columns() -> None:
    """Fügt fehlende Spalten zur remotes-Tabelle hinzu (Schema-Migration)."""
    con  = _conn()
    # Tabelle existiert evtl. noch als 'wol' → umbenennen
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "wol" in tables and "remotes" not in tables:
        con.execute("ALTER TABLE wol RENAME TO remotes")
        con.commit()
        print("[storage] Migration: Tabelle wol → remotes umbenannt")
    cols = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}
    if "ssh_user" not in cols:
        con.execute("ALTER TABLE remotes ADD COLUMN ssh_user TEXT NOT NULL DEFAULT 'root'")
        con.commit()
        print("[storage] Migration: remotes.ssh_user hinzugefügt")


def init_db() -> None:
    con = _conn()
    for ddl in _DDL.values():
        con.execute(ddl)
    con.commit()
    _migrate_remotes_columns()
    _migrate_all_yaml()


# ── Konvertierung DB-Row ↔ Python-dict ───────────────────────────

def _row_to_dict(module: str, row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    d["enabled"] = bool(d.get("enabled", 1))
    list_fields = _LIST_FIELDS.get(module, [])
    for field in list_fields:
        raw = d.get(field)
        d[field] = [l for l in raw.split("\n") if l] if raw else []
    # Rückwärtskompatibilität: borg pre/post_hooks → pre/post
    if module == "borg":
        d["pre"]  = d.pop("pre_hooks",  [])
        d["post"] = d.pop("post_hooks", [])
    # proxmox_hosts extra_sources → source
    if module == "proxmox_hosts":
        d["source"] = d.pop("extra_sources", [])
    return d


def _to_list(val) -> list:
    """Stellt sicher dass val eine Liste ist – kein versehentliches char-join."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [l for l in val.split("\n") if l]
    return list(val)


def _dict_to_params(module: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Python-dict → DB-Parameter-dict."""
    p = dict(item)
    p["enabled"] = 1 if item.get("enabled", True) else 0

    if module == "borg":
        p["pre_hooks"]  = "\n".join(_to_list(item.get("pre")))
        p["post_hooks"] = "\n".join(_to_list(item.get("post")))
        p["exclude"]    = "\n".join(_to_list(item.get("exclude")))
        p.pop("pre",  None)
        p.pop("post", None)

    if module == "proxmox_hosts":
        p["extra_sources"] = "\n".join(_to_list(item.get("source")))
        p.pop("source", None)

    # DB-PK nie als Parameter mitgeben (AUTOINCREMENT)
    p.pop("id", None)
    return p


# ── Öffentliche API ───────────────────────────────────────────────

def load_config(module: str) -> Dict[str, Any]:
    """Gibt {str(id): item_dict} zurück – identische Struktur wie früher."""
    rows = _conn().execute(
        f"SELECT * FROM {module} ORDER BY id"
    ).fetchall()
    return {str(row["id"]): _row_to_dict(module, row) for row in rows}


def get_item(module: str, item_id) -> Optional[Dict[str, Any]]:
    if item_id is None:
        return None
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        return None
    row = _conn().execute(
        f"SELECT * FROM {module} WHERE id=?", (iid,)
    ).fetchone()
    return _row_to_dict(module, row) if row else None


def save_item(module: str, item_id, item: dict) -> None:
    if item is None or not isinstance(item, dict):
        raise TypeError("item muss ein dict sein")
    p = _dict_to_params(module, item)
    con = _conn()

    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        iid = None

    if iid:
        # UPDATE falls vorhanden
        existing = con.execute(
            f"SELECT id FROM {module} WHERE id=?", (iid,)
        ).fetchone()
        if existing:
            sets   = ", ".join(f"{k}=?" for k in p)
            values = list(p.values()) + [iid]
            con.execute(f"UPDATE {module} SET {sets} WHERE id=?", values)
            con.commit()
            return

    # INSERT (neuer Eintrag)
    cols   = ", ".join(p.keys())
    placeholders = ", ".join("?" * len(p))
    con.execute(
        f"INSERT INTO {module} ({cols}) VALUES ({placeholders})",
        list(p.values())
    )
    con.commit()


def delete_item(module: str, item_id) -> bool:
    try:
        iid = int(item_id)
    except (ValueError, TypeError):
        return False
    cur = _conn().execute(f"DELETE FROM {module} WHERE id=?", (iid,))
    _conn().commit()
    return cur.rowcount > 0


def next_item_id(module: str) -> str:
    """Nächste freie ID (für Formulare die eine neue ID brauchen)."""
    row = _conn().execute(
        f"SELECT COALESCE(MAX(id), 0) + 1 AS next FROM {module}"
    ).fetchone()
    return str(row["next"])


# ── YAML-Migration ────────────────────────────────────────────────

def _migrate_all_yaml() -> None:
    for module in _DDL.keys():
        yaml_path = CONFIG_DIR / f"{module}.yaml"
        if not yaml_path.exists():
            continue
        # Schon Daten in DB? → skip
        count = _conn().execute(
            f"SELECT COUNT(*) AS c FROM {module}"
        ).fetchone()["c"]
        if count > 0:
            yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
            continue
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for key, value in raw.items():
                # proxmox_lxc: YAML-Feld "id" = Container-ID → "vmid" in DB
                if module == "proxmox_lxc" and "id" in value and "vmid" not in value:
                    value = dict(value)
                    value["vmid"] = value.pop("id")
                save_item(module, key, value)
            yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
            print(f"[storage] Migriert: {module} ({len(raw)} Einträge)")
        except Exception as e:
            print(f"[storage] Migration fehlgeschlagen für {module}: {e}")


# ── Settings-Tabelle (key/value) ──────────────────────────────────

_SETTINGS_DDL = """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    )
"""


def _init_settings() -> None:
    _conn().execute(_SETTINGS_DDL)
    _conn().commit()


def get_setting(key: str, default: str = "") -> str:
    _init_settings()
    row = _conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    _init_settings()
    _conn().execute(
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    _conn().commit()


# ══════════════════════════════════════════════════════════════════
#  Borg Repository Storage
# ══════════════════════════════════════════════════════════════════

_REPOS_DDL = """
    CREATE TABLE IF NOT EXISTS borg_repos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        path        TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        encryption  TEXT DEFAULT 'repokey-blake2',
        created_at  TEXT DEFAULT (datetime('now'))
    )
"""


def _init_repos() -> None:
    _conn().execute(_REPOS_DDL)
    _conn().commit()


def list_repos() -> list:
    _init_repos()
    rows = _conn().execute(
        "SELECT id, name, path, description, encryption, created_at FROM borg_repos ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_repo(repo_id: int) -> dict | None:
    _init_repos()
    row = _conn().execute(
        "SELECT id, name, path, description, encryption, created_at FROM borg_repos WHERE id=?",
        (repo_id,)
    ).fetchone()
    return dict(row) if row else None


def get_repo_by_path(path: str) -> dict | None:
    _init_repos()
    row = _conn().execute(
        "SELECT id, name, path, description, encryption, created_at FROM borg_repos WHERE path=?",
        (path,)
    ).fetchone()
    return dict(row) if row else None


def create_repo(name: str, path: str, description: str = "", encryption: str = "repokey-blake2") -> int:
    _init_repos()
    cur = _conn().execute(
        "INSERT INTO borg_repos (name, path, description, encryption) VALUES (?,?,?,?)",
        (name, path, description, encryption)
    )
    _conn().commit()
    return cur.lastrowid


def update_repo(repo_id: int, name: str, path: str, description: str = "") -> None:
    _init_repos()
    _conn().execute(
        "UPDATE borg_repos SET name=?, path=?, description=? WHERE id=?",
        (name, path, description, repo_id)
    )
    _conn().commit()


def delete_repo(repo_id: int) -> bool:
    _init_repos()
    cur = _conn().execute("DELETE FROM borg_repos WHERE id=?", (repo_id,))
    _conn().commit()
    return cur.rowcount > 0


# ── Job-History ───────────────────────────────────────────────────────────────

_HISTORY_DDL = """
    CREATE TABLE IF NOT EXISTS job_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at  TEXT    NOT NULL,
        finished_at TEXT,
        module      TEXT    NOT NULL DEFAULT '',
        item_id     TEXT    NOT NULL DEFAULT '',
        description TEXT    NOT NULL DEFAULT '',
        status      TEXT    NOT NULL DEFAULT 'running',
        duration_s  INTEGER,
        mode        TEXT    NOT NULL DEFAULT 'run'
    )
"""

def _init_history() -> None:
    _conn().execute(_HISTORY_DDL)
    _conn().commit()


def history_start(module: str, item_id: str, description: str, mode: str = "run") -> int:
    """Schreibt einen neuen History-Eintrag und gibt die ID zurück."""
    _init_history()
    from datetime import datetime
    cur = _conn().execute(
        "INSERT INTO job_history (started_at, module, item_id, description, status, mode) VALUES (?,?,?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), module, item_id, description, "running", mode)
    )
    _conn().commit()
    return cur.lastrowid


def history_finish(history_id: int, status: str, duration_s: int) -> None:
    """Schließt einen History-Eintrag ab."""
    _init_history()
    from datetime import datetime
    _conn().execute(
        "UPDATE job_history SET finished_at=?, status=?, duration_s=? WHERE id=?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, duration_s, history_id)
    )
    _conn().commit()


def list_history(limit: int = 100, module: str = None) -> list:
    """Gibt Job-History zurück, neueste zuerst."""
    _init_history()
    if module:
        rows = _conn().execute(
            "SELECT * FROM job_history WHERE module=? ORDER BY id DESC LIMIT ?",
            (module, limit)
        ).fetchall()
    else:
        rows = _conn().execute(
            "SELECT * FROM job_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Borg Archive Cache ────────────────────────────────────────────────────────

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
    from datetime import datetime
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
    from datetime import datetime
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
    """True wenn das Archiv im Archive-Cache registriert ist (auch wenn Datei-Cache leer ist)."""
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


_STATS_CACHE_DDL = """
    CREATE TABLE IF NOT EXISTS borg_stats_cache (
        item_id   TEXT PRIMARY KEY,
        stats_json TEXT NOT NULL,
        cached_at  TEXT NOT NULL
    )
"""


def _init_stats_cache() -> None:
    _conn().execute(_STATS_CACHE_DDL)
    _conn().commit()


def save_stats_cache(item_id: str, info: dict) -> str:
    """Speichert borg info --json Ausgabe. Gibt cached_at zurück."""
    import json as _json
    _init_stats_cache()
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _conn().execute(
        "INSERT INTO borg_stats_cache (item_id, stats_json, cached_at) VALUES (?,?,?) "
        "ON CONFLICT(item_id) DO UPDATE SET stats_json=excluded.stats_json, cached_at=excluded.cached_at",
        (item_id, _json.dumps(info), now),
    )
    _conn().commit()
    return now


def get_stats_cache(item_id: str) -> tuple:
    """Gibt (info_dict, cached_at) zurück, oder (None, None) wenn kein Cache."""
    import json as _json
    _init_stats_cache()
    row = _conn().execute(
        "SELECT stats_json, cached_at FROM borg_stats_cache WHERE item_id=?", (item_id,)
    ).fetchone()
    if not row:
        return None, None
    return _json.loads(row["stats_json"]), row["cached_at"]


def save_file_cache_for_archive(item_id: str, archive: str, entries: list) -> None:
    """Speichert Dateieinträge für ein einzelnes Archiv (ersetzt ggf. vorhandene)."""
    _init_archive_cache()
    con = _conn()
    con.execute(
        "DELETE FROM borg_file_cache WHERE item_id=? AND archive=?", (item_id, archive)
    )
    con.executemany(
        "INSERT INTO borg_file_cache (item_id, archive, path, type, size, mtime, mode) "
        "VALUES (?,?,?,?,?,?,?)",
        [(item_id, archive,
          e.get("path", ""), e.get("type", ""),
          e.get("size", 0), e.get("mtime", ""), e.get("mode", ""))
         for e in entries],
    )
    con.commit()
