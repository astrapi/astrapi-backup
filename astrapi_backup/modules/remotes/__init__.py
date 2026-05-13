from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

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

register_table(_KEY, _DDL, list_fields=["types"], secret_fields=["api_token_secret"])

from astrapi_core.ui.controls import Col, ContentTable  # noqa: E402

from astrapi_backup.modules.remotes.ui.crud import api_router as router
from astrapi_backup.modules.remotes.ui.crud import router as ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_content=ContentTable(
        has_run_buttons=False,
        columns=[
            Col.badge_list(
                "types",
                "Typen",
                {
                    "borg_source": {"label": "Borg Source", "cls": "badge-live"},
                    "borg_target": {"label": "Borg Target", "cls": "badge-live"},
                    "rsync": {"label": "Rsync", "cls": "badge-live"},
                    "proxmox_node": {"label": "Proxmox Node", "cls": "badge-warn"},
                    "proxmox_host": {"label": "Proxmox Host", "cls": "badge-warn"},
                    "proxmox_backup": {"label": "Proxmox Backup", "cls": "badge-muted"},
                },
            ),
            Col.mono("ssh_user", "SSH-Benutzer"),
            Col.mono("mac", "MAC"),
        ],
    ),
)

try:
    from .jobs import sync_all_item_actions

    sync_all_item_actions()
except Exception:
    pass
