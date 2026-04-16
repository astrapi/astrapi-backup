# api/storage.py
"""SQLite-Backend mit einer Tabelle pro Modul."""

from astrapi.core.system.db import (
    configure as _configure_db,
    register_table, create_all_registered_tables,
    load_config, get_item, save_item, delete_item, next_item_id, get_entry, patch_item,
)
from astrapi.core.system.activity_log import (
    log_activity, update_activity_log,
    list_activity, get_activity_log, clear_activity_log,
    get_latest_activity_log_id, list_runs_for_item,
    history_start, history_finish, list_history,
    append_log_line, get_log_lines,
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
        "col_in":  {"pre_hooks": "pre", "post_hooks": "post"},
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
        "col_in":  {"extra_sources": "source"},
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


def init_db() -> None:
    _configure_db(DB_PATH)
    _register_app_tables()
    create_all_registered_tables()


# Borg-spezifischer Cache → app/modules/borg/storage.py
from astrapi_backup.modules.borg.storage import (
    save_archive_list_cache, save_archive_cache,
    get_archive_cache, archive_is_cached,
    get_file_cache, save_file_cache_for_archive,
    get_stats_cache, save_stats_cache,
)
