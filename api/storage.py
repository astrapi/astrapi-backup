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

DB_PATH    = Path("data/backupctl.db")
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

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
}

# Felder die Listen sind (newline-getrennt in DB, list in Python)
_LIST_FIELDS = {
    "borg":          ["pre_hooks", "post_hooks", "exclude"],
    "proxmox_hosts": ["extra_sources"],
}


def init_db() -> None:
    con = _conn()
    for ddl in _DDL.values():
        con.execute(ddl)
    con.commit()
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
