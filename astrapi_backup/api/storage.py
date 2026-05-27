# api/storage.py
"""SQLite-Backend mit einer Tabelle pro Modul."""

from astrapi_core.system.db import (
    configure as _configure_db,
)
from astrapi_core.system.db import (
    create_all_registered_tables,
    register_table,
    load_config,
    get_item,
    get_entry,
    patch_item,
)

from astrapi_backup._paths import db_path as _db_path

DB_PATH = _db_path()


# ── App-Tabellen-Konfiguration ─────────────────────────────────────

_APP_TABLES = {
    "borg": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS borg (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled          INTEGER NOT NULL DEFAULT 1,
                description      TEXT    NOT NULL DEFAULT '',
                source_remote_id TEXT,
                source_path      TEXT    NOT NULL DEFAULT '',
                target_remote_id TEXT,
                target_path      TEXT    NOT NULL DEFAULT '',
                pre_hooks        TEXT,
                post_hooks       TEXT,
                exclude          TEXT,
                last_run         TEXT,
                last_status      TEXT
            )""",
        "list_fields": ["pre_hooks", "post_hooks", "exclude"],
        "col_in": {"pre_hooks": "pre", "post_hooks": "post"},
        "col_out": {"pre": "pre_hooks", "post": "post_hooks"},
    },
    "rsync": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS rsync (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled          INTEGER NOT NULL DEFAULT 1,
                description      TEXT    NOT NULL DEFAULT '',
                type             TEXT    NOT NULL DEFAULT '',
                source_remote_id TEXT,
                source_path      TEXT    NOT NULL DEFAULT '',
                target_remote_id TEXT,
                target_path      TEXT    NOT NULL DEFAULT '',
                last_run         TEXT,
                last_status      TEXT
            )""",
    },
    "proxmox_lxc": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_lxc (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vmid        INTEGER NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                node        TEXT    NOT NULL DEFAULT '',
                enabled     INTEGER NOT NULL DEFAULT 1,
                last_run    TEXT,
                last_status TEXT
            )""",
    },
    "proxmox_hosts": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_hosts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                description   TEXT    NOT NULL DEFAULT '',
                enabled       INTEGER NOT NULL DEFAULT 1,
                remote_id     TEXT,
                extra_sources TEXT,
                last_run      TEXT,
                last_status   TEXT
            )""",
        "list_fields": ["extra_sources"],
        "col_in": {"extra_sources": "source"},
        "col_out": {"source": "extra_sources"},
    },
    "proxmox_jobs": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job         TEXT    NOT NULL DEFAULT '',
                remote_id   TEXT,
                type        TEXT    NOT NULL DEFAULT '',
                enabled     INTEGER NOT NULL DEFAULT 1,
                last_run    TEXT,
                last_status TEXT
            )""",
    },
}


def _register_app_tables() -> None:
    for key, cfg in _APP_TABLES.items():
        register_table(
            key,
            cfg["ddl"],
            list_fields=cfg.get("list_fields"),
            col_in=cfg.get("col_in"),
            col_out=cfg.get("col_out"),
        )


def _run_migrations() -> None:
    """Fügt fehlende Spalten zu bestehenden Tabellen hinzu (ALTER TABLE … ADD COLUMN)."""
    from astrapi_core.system.db import _conn

    con = _conn()
    _migrations = [
        ("remotes", "ssh_connect_timeout", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for table, column, col_def in _migrations:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            con.commit()
        except Exception:
            pass  # Spalte existiert bereits


def init_db() -> None:
    _configure_db(DB_PATH)
    _register_app_tables()
    create_all_registered_tables()
    _run_migrations()


# Borg-spezifischer Cache → app/modules/borg/cache/storage.py
