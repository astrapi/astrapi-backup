from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from astrapi.core.system.db import register_table

_DDL = """
    CREATE TABLE IF NOT EXISTS remotes (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        mac                  TEXT    NOT NULL DEFAULT '',
        host                 TEXT    NOT NULL DEFAULT '',
        description          TEXT    NOT NULL DEFAULT '',
        ssh_user             TEXT    NOT NULL DEFAULT 'backupadm',
        ssh_port             INTEGER NOT NULL DEFAULT 22,
        enabled              INTEGER NOT NULL DEFAULT 1,
        borg_bin             TEXT    NOT NULL DEFAULT '',
        types                TEXT    NOT NULL DEFAULT '',
        pve_api_token_id     TEXT    NOT NULL DEFAULT '',
        pve_api_token_secret TEXT    NOT NULL DEFAULT '',
        pve_verify_ssl       INTEGER NOT NULL DEFAULT 0
    )"""

register_table("remotes", _DDL, list_fields=["types"])


def _migrate():
    """Fügt fehlende Spalten zu bestehenden Datenbanken hinzu."""
    from astrapi.core.system.db import _conn
    con = _conn()
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}
    if "ssh_port" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN ssh_port INTEGER NOT NULL DEFAULT 22")
    if "borg_bin" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN borg_bin TEXT NOT NULL DEFAULT ''")
    if "types" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN types TEXT NOT NULL DEFAULT ''")
    if "pve_api_token_id" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN pve_api_token_id TEXT NOT NULL DEFAULT ''")
    if "pve_api_token_secret" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN pve_api_token_secret TEXT NOT NULL DEFAULT ''")
    if "pve_verify_ssl" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN pve_verify_ssl INTEGER NOT NULL DEFAULT 0")
    con.commit()

try:
    _migrate()
except Exception:
    pass

from .api import router
from .ui import router as ui_router

module = load_modul(Path(__file__).parent, "remotes", router, ui_router)

try:
    from .jobs import sync_all_item_actions
    sync_all_item_actions()
except Exception:
    pass
