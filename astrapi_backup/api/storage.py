# api/storage.py
"""
SQLite-Backend mit einer Tabelle pro Modul, echten Spalten.
Listen (pre, post, exclude, source) werden newline-getrennt als TEXT gespeichert.

Migration: bestehende YAML-Dateien werden einmalig importiert,
danach in config/*.yaml.migrated umbenannt.
"""

import sqlite3
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrapi.core.system.db import (
    configure as _configure_db,
    _conn,
    get_setting, set_setting,
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

from astrapi_backup._paths import db_path as _db_path, work_dir as _work_dir
DB_PATH    = _db_path()
CONFIG_DIR = _work_dir() / "config"


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
                exclude          TEXT
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
                source_remote_id TEXT,
                source_host      TEXT    NOT NULL DEFAULT '',
                source_path      TEXT    NOT NULL DEFAULT '',
                target_remote_id TEXT,
                target_host      TEXT    NOT NULL DEFAULT '',
                target_path      TEXT    NOT NULL DEFAULT ''
            )""",
    },

    "proxmox_lxc": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_lxc (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vmid        INTEGER NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                node        TEXT    NOT NULL DEFAULT '',
                remote_id   TEXT,
                enabled     INTEGER NOT NULL DEFAULT 1
            )""",
    },

    "proxmox_hosts": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_hosts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                host           TEXT    NOT NULL DEFAULT '',
                description    TEXT    NOT NULL DEFAULT '',
                enabled        INTEGER NOT NULL DEFAULT 1,
                namespace      TEXT    NOT NULL DEFAULT 'host',
                remote_id      TEXT,
                extra_sources  TEXT
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
                enabled     INTEGER NOT NULL DEFAULT 1
            )""",
    },
}

# App-Modul-Keys für YAML-Migration (kein remotes – lebt jetzt in core)
_APP_MODULE_KEYS = list(_APP_TABLES.keys())


def _register_app_tables() -> None:
    """Registriert alle App-Tabellen in der generischen CRUD-Registry."""
    for key, cfg in _APP_TABLES.items():
        register_table(
            key,
            cfg["ddl"],
            list_fields=cfg.get("list_fields"),
            col_in=cfg.get("col_in"),
            col_out=cfg.get("col_out"),
        )


# ── Schema-Migrationen ────────────────────────────────────────────

def _migrate_remotes_columns() -> None:
    """Backward-compat: remotes-Tabelle aus alten Versionen migrieren."""
    con = _conn()
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "wol" in tables and "remotes" not in tables:
        con.execute("ALTER TABLE wol RENAME TO remotes")
        con.commit()
        print("[storage] Migration: Tabelle wol → remotes umbenannt")
    if "remotes" not in tables:
        return
    cols = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}
    if "ssh_user" not in cols:
        con.execute("ALTER TABLE remotes ADD COLUMN ssh_user TEXT NOT NULL DEFAULT 'root'")
        con.commit()
        print("[storage] Migration: remotes.ssh_user hinzugefügt")


def _migrate_proxmox_hosts_columns() -> None:
    """Backward-compat: proxmox_hosts.namespace hinzufügen."""
    con = _conn()
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "proxmox_hosts" not in tables:
        return
    cols = {row[1] for row in con.execute("PRAGMA table_info(proxmox_hosts)").fetchall()}
    if "namespace" not in cols:
        con.execute("ALTER TABLE proxmox_hosts ADD COLUMN namespace TEXT NOT NULL DEFAULT 'host'")
        con.commit()
        print("[storage] Migration: proxmox_hosts.namespace hinzugefügt")


def _migrate_remote_id_columns() -> None:
    """Fügt remote_id / source_remote_id / target_remote_id zu bestehenden Tabellen hinzu."""
    con = _conn()
    migrations = [
        ("borg",          "source_remote_id", "ALTER TABLE borg          ADD COLUMN source_remote_id TEXT"),
        ("borg",          "target_remote_id", "ALTER TABLE borg          ADD COLUMN target_remote_id TEXT"),
        ("rsync",         "source_remote_id", "ALTER TABLE rsync         ADD COLUMN source_remote_id TEXT"),
        ("rsync",         "target_remote_id", "ALTER TABLE rsync         ADD COLUMN target_remote_id TEXT"),
        ("proxmox_jobs",  "remote_id",        "ALTER TABLE proxmox_jobs  ADD COLUMN remote_id        TEXT"),
        ("proxmox_lxc",   "remote_id",        "ALTER TABLE proxmox_lxc   ADD COLUMN remote_id        TEXT"),
        ("proxmox_hosts", "remote_id",        "ALTER TABLE proxmox_hosts ADD COLUMN remote_id        TEXT"),
    ]
    for table, col, sql in migrations:
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in existing:
            con.execute(sql)
    con.commit()


def _migrate_borg_drop_legacy_columns() -> None:
    """Entfernt veraltete Spalten source_host, target_host, ssh_user aus der borg-Tabelle."""
    con = _conn()
    existing = {row[1] for row in con.execute("PRAGMA table_info(borg)").fetchall()}
    for col in ("source_host", "target_host", "ssh_user"):
        if col in existing:
            try:
                con.execute(f"ALTER TABLE borg DROP COLUMN {col}")
            except Exception:
                pass
    con.commit()


def _migrate_last_run_columns() -> None:
    """Fügt last_run und last_status TEXT zu allen Job-Tabellen hinzu."""
    con = _conn()
    for table in ("borg", "rsync", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts"):
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if "last_run" not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN last_run TEXT")
        if "last_status" not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN last_status TEXT")
    con.commit()


def _migrate_proxmox_jobs_drop_columns() -> None:
    """Entfernt obsolete Spalten description und host aus proxmox_jobs."""
    con = _conn()
    existing = {row[1] for row in con.execute("PRAGMA table_info(proxmox_jobs)").fetchall()}
    for col in ("description", "host"):
        if col in existing:
            try:
                con.execute(f"ALTER TABLE proxmox_jobs DROP COLUMN {col}")
            except Exception:
                pass
    con.commit()


def init_db() -> None:
    _configure_db(DB_PATH)
    _register_app_tables()
    create_all_registered_tables()
    _migrate_remotes_columns()
    _migrate_proxmox_hosts_columns()
    _migrate_remote_id_columns()
    _migrate_last_run_columns()
    _migrate_proxmox_jobs_drop_columns()
    _migrate_borg_drop_legacy_columns()
    _migrate_all_yaml()


# ── YAML-Migration ────────────────────────────────────────────────

def _migrate_all_yaml() -> None:
    for module in _APP_MODULE_KEYS:
        yaml_path = CONFIG_DIR / f"{module}.yaml"
        if not yaml_path.exists():
            continue
        count = _conn().execute(
            f"SELECT COUNT(*) AS c FROM {module}"
        ).fetchone()["c"]
        if count > 0:
            yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
            continue
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for key, value in raw.items():
                if module == "proxmox_lxc" and "id" in value and "vmid" not in value:
                    value = dict(value)
                    value["vmid"] = value.pop("id")
                save_item(module, key, value)
            yaml_path.rename(yaml_path.with_suffix(".yaml.migrated"))
            print(f"[storage] Migriert: {module} ({len(raw)} Einträge)")
        except Exception as e:
            print(f"[storage] Migration fehlgeschlagen für {module}: {e}")


# Borg-spezifischer Cache → app/modules/borg/storage.py
from astrapi_backup.modules.borg.storage import (
    save_archive_list_cache, save_archive_cache,
    get_archive_cache, archive_is_cached,
    get_file_cache, save_file_cache_for_archive,
    get_stats_cache, save_stats_cache,
)
