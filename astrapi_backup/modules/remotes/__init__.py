from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS remotes (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        mac              TEXT    NOT NULL DEFAULT '',
        host             TEXT    NOT NULL DEFAULT '',
        ssh_user              TEXT    NOT NULL DEFAULT 'backupadm',
        ssh_port              INTEGER NOT NULL DEFAULT 22,
        ssh_connect_timeout   INTEGER NOT NULL DEFAULT 0,
        enabled               INTEGER NOT NULL DEFAULT 1,
        borg_bin         TEXT    NOT NULL DEFAULT '',
        types            TEXT    NOT NULL DEFAULT '',
        api_token_id     TEXT    NOT NULL DEFAULT '',
        api_token_secret TEXT    NOT NULL DEFAULT '',
        api_verify_ssl   INTEGER NOT NULL DEFAULT 0,
        pbs_fingerprint  TEXT    NOT NULL DEFAULT '',
        pbs_datastore    TEXT    NOT NULL DEFAULT ''
    )"""

register_table(_KEY, _DDL, list_fields=["types"], secret_fields=["api_token_secret"])

from urllib.parse import parse_qs as _parse_qs
from urllib.parse import urlparse

# Remote-Host-Resolver für resolve_remote_host() in Templates registrieren
from astrapi_core.ui.app import register_remote_resolver as _reg_remote_resolver
from astrapi_core.ui.controls import Col, ContentTable  # noqa: E402

# Dynamische Feld-Optionen für options_endpoint in schema.yaml registrieren
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg


def _remote_host_fn(remote_id) -> str:
    from astrapi_backup.modules.remotes.service import get_remote

    r = get_remote(remote_id)
    return r.get("host") or "—" if r else "—"


_reg_remote_resolver(_remote_host_fn)

from astrapi_backup.modules.remotes.ui.crud import api_router as router
from astrapi_backup.modules.remotes.ui.crud import router as ui_router


def _remotes_options_fetcher(endpoint: str) -> list:
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select

    qs = _parse_qs(urlparse(endpoint).query)
    type_filter = qs.get("type", [None])[0]
    include_local = qs.get("local", ["1"])[0] != "0"
    return [
        {"value": r["id"], "label": r["label"]}
        for r in get_all_remotes_for_select(type_filter=type_filter, include_local=include_local)
    ]


_reg("/api/remotes/for-select", _remotes_options_fetcher)

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
