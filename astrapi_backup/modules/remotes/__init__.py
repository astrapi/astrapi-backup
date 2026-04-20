from pathlib import Path
from astrapi_core.ui.module_loader import load_modul
from astrapi_core.system.db import register_table

_DDL = """
    CREATE TABLE IF NOT EXISTS remotes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        mac              TEXT    NOT NULL DEFAULT '',
        host             TEXT    NOT NULL DEFAULT '',
        ssh_user         TEXT    NOT NULL DEFAULT 'backupadm',
        ssh_port         INTEGER NOT NULL DEFAULT 22,
        enabled          INTEGER NOT NULL DEFAULT 1,
        borg_bin         TEXT    NOT NULL DEFAULT '',
        types            TEXT    NOT NULL DEFAULT '',
        api_token_id     TEXT    NOT NULL DEFAULT '',
        api_token_secret TEXT    NOT NULL DEFAULT '',
        api_verify_ssl   INTEGER NOT NULL DEFAULT 0,
        pbs_fingerprint  TEXT    NOT NULL DEFAULT '',
        pbs_datastore    TEXT    NOT NULL DEFAULT ''
    )"""

register_table("remotes", _DDL, list_fields=["types"], secret_fields=["api_token_secret"])

from .api import router
from .ui import router as ui_router

module = load_modul(Path(__file__).parent, "remotes", router, ui_router)

try:
    from .jobs import sync_all_item_actions
    sync_all_item_actions()
except Exception:
    pass
