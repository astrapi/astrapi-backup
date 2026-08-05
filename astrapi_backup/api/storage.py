# api/storage.py
"""SQLite-Backend mit einer Tabelle pro Modul."""

import logging

from astrapi_core.system.db import (
    configure as _configure_db,
)
from astrapi_core.system.db import (
    create_all_registered_tables,
    register_table,
)

from astrapi_backup._paths import db_path as _db_path

DB_PATH = _db_path()

log = logging.getLogger(__name__)


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
                last_status      TEXT,
                last_log         TEXT
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
    "proxmox_client": {
        "ddl": """
            CREATE TABLE IF NOT EXISTS proxmox_client (
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
                last_status TEXT,
                last_log    TEXT
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


# Tabellen, die in früheren Versionen anders hießen
_RENAMES = [
    ("proxmox_hosts", "proxmox_client"),
]


def _table_exists(con, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _run_table_renames() -> None:
    """Benennt Tabellen aus früheren Versionen um.

    Läuft VOR create_all_registered_tables(): sonst existiert die Zieltabelle
    bereits (leer, per CREATE TABLE IF NOT EXISTS) und das RENAME scheitert.

    Ist auf einer Instanz beides vorhanden – alte Tabelle mit Daten, neue leer –
    dann wurde genau dieser Fall schon ausgelöst. Die Zeilen werden dann über
    die gemeinsamen Spaltennamen kopiert (nicht per SELECT *, die Reihenfolge
    kann abweichen) und die alte Tabelle als `<name>_alt` beiseitegelegt.
    """
    from astrapi_core.system.db import _conn

    con = _conn()
    for old, new in _RENAMES:
        if not _table_exists(con, old):
            continue

        if not _table_exists(con, new):
            con.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')
            con.commit()
            log.info("DB-Migration: Tabelle %s → %s umbenannt", old, new)
            continue

        # Beide vorhanden: nur zusammenführen wenn die neue leer ist.
        count = con.execute(f'SELECT count(*) FROM "{new}"').fetchone()[0]
        if count:
            log.warning(
                "DB-Migration: %s und %s existieren beide und %s enthält %d Zeilen – "
                "kein automatisches Zusammenführen, bitte manuell prüfen",
                old, new, new, count,
            )
            continue

        shared = [c for c in _columns(con, old) if c in _columns(con, new)]
        if not shared:
            log.warning("DB-Migration: %s und %s haben keine gemeinsamen Spalten", old, new)
            continue

        cols = ", ".join(f'"{c}"' for c in shared)
        con.execute(f'INSERT INTO "{new}" ({cols}) SELECT {cols} FROM "{old}"')
        con.execute(f'ALTER TABLE "{old}" RENAME TO "{old}_alt"')
        con.commit()
        log.info(
            "DB-Migration: %d Zeilen aus %s nach %s übernommen, alte Tabelle als %s_alt gesichert",
            con.execute(f'SELECT count(*) FROM "{new}"').fetchone()[0], old, new, old,
        )


def _run_column_migrations() -> None:
    """Fügt fehlende Spalten zu bestehenden Tabellen hinzu."""
    from astrapi_core.system.db import _conn

    con = _conn()
    _migrations = [
        ("remotes", "ssh_connect_timeout", "INTEGER NOT NULL DEFAULT 0"),
        ("remotes", "poweroff_cmd", "TEXT NOT NULL DEFAULT 'sudo shutdown -h now'"),
        ("rsync", "last_log", "TEXT"),
        ("proxmox_jobs", "last_log", "TEXT"),
    ]
    for table, column, col_def in _migrations:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            con.commit()
        except Exception:
            pass  # Spalte existiert bereits


def _run_scheduler_step_renames() -> None:
    """Zieht umbenannte Modul-Keys in gespeicherten Scheduler-Schritten nach.

    Scheduler-Jobs liegen als JSON im kvstore (collection "scheduler_jobs") und
    verweisen ueber "<modul>.<aktion>" auf registrierte Aktionen. Beim Umbenennen
    eines Moduls (T-023) wurde nur die Tabelle migriert -- die Schritte zeigten
    weiter auf den alten Key. Der Scheduler findet die Aktion dann nicht und
    quittiert jeden Lauf mit "Unbekannte Aktion: proxmox_hosts.run".
    """
    from astrapi_core.system.db import _conn

    con = _conn()
    for old, new in _RENAMES:
        alt, neu = f"{old}.", f"{new}."
        try:
            cur = con.execute(
                "UPDATE kvstore SET value = replace(value, ?, ?) "
                "WHERE collection = 'scheduler_jobs' AND value LIKE ?",
                (alt, neu, f"%{alt}%"),
            )
            con.commit()
            if cur.rowcount:
                log.info(
                    "DB-Migration: %d Scheduler-Job(s) von %s auf %s umgestellt",
                    cur.rowcount, old, new,
                )
        except Exception as e:
            log.warning("DB-Migration: Scheduler-Schritte %s → %s: %s", old, new, e)


def init_db() -> None:
    _configure_db(DB_PATH)
    _register_app_tables()
    _run_table_renames()          # vor dem Anlegen: sonst ist das Ziel schon da
    create_all_registered_tables()
    _run_column_migrations()      # nach dem Anlegen: braucht die Tabellen
    _run_scheduler_step_renames()

    # Beim Start kann nichts laufen: was noch auf "running" steht, stammt aus
    # einem abgebrochenen Lauf (Neustart, Absturz, Update).
    from astrapi_core.system.db import reset_stale_status

    reset_stale_status()


# Borg-spezifischer Cache → app/modules/borg/cache/storage.py
