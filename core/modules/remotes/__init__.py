from pathlib import Path
from core.ui.module_loader import load_modul
from core.system.db import register_table

_DDL = """
    CREATE TABLE IF NOT EXISTS remotes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        mac         TEXT    NOT NULL DEFAULT '',
        host        TEXT    NOT NULL DEFAULT '',
        description TEXT    NOT NULL DEFAULT '',
        ssh_user    TEXT    NOT NULL DEFAULT 'root',
        enabled     INTEGER NOT NULL DEFAULT 1
    )"""

register_table("remotes", _DDL)

from .api import router
from .ui import bp

module = load_modul(Path(__file__).parent, "remotes", router, bp)

try:
    from .jobs import sync_all_item_actions
    sync_all_item_actions()
except Exception:
    pass
