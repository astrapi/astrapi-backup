from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from astrapi.core.system.db import register_table

_DDL = """
    CREATE TABLE IF NOT EXISTS remotes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        mac         TEXT    NOT NULL DEFAULT '',
        host        TEXT    NOT NULL DEFAULT '',
        description TEXT    NOT NULL DEFAULT '',
        ssh_user    TEXT    NOT NULL DEFAULT 'backupadm',
        ssh_port    INTEGER NOT NULL DEFAULT 22,
        enabled     INTEGER NOT NULL DEFAULT 1
    )"""

register_table("remotes", _DDL)


def _migrate():
    """Fügt fehlende Spalten zu bestehenden Datenbanken hinzu."""
    from astrapi.core.system.db import _conn
    con = _conn()
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}
    if "ssh_port" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN ssh_port INTEGER NOT NULL DEFAULT 22")
    if "borg_bin" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN borg_bin TEXT NOT NULL DEFAULT ''")
    con.commit()

try:
    _migrate()
except Exception:
    pass

from .api import router
from .ui import bp

module = load_modul(Path(__file__).parent, "remotes", router, bp)

try:
    from .jobs import sync_all_item_actions
    sync_all_item_actions()
except Exception:
    pass
