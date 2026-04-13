from pathlib import Path
from astrapi.core.ui.module_loader import load_modul
from astrapi.core.system.db import register_table

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
        api_verify_ssl   INTEGER NOT NULL DEFAULT 0
    )"""

register_table("remotes", _DDL, list_fields=["types"])


def _migrate():
    """Migriert die remotes-Tabelle auf den aktuellen Stand."""
    from astrapi.core.system.db import _conn
    con = _conn()
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}

    # Altlasten sicherstellen bevor Migration
    if "ssh_port" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN ssh_port INTEGER NOT NULL DEFAULT 22")
    if "borg_bin" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN borg_bin TEXT NOT NULL DEFAULT ''")
    if "types" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN types TEXT NOT NULL DEFAULT ''")

    # Sicherstellen dass alte Spalten existieren (für Datenmigration)
    for col, ddl in [
        ("pve_api_token_id",     "TEXT NOT NULL DEFAULT ''"),
        ("pve_api_token_secret", "TEXT NOT NULL DEFAULT ''"),
        ("pve_verify_ssl",       "INTEGER NOT NULL DEFAULT 0"),
        ("pbs_token_id",         "TEXT NOT NULL DEFAULT ''"),
        ("pbs_token_secret",     "TEXT NOT NULL DEFAULT ''"),
        ("pbs_verify_ssl",       "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in existing:
            con.execute(f"ALTER TABLE remotes ADD COLUMN {col} {ddl}")

    con.commit()
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}

    # Neue einheitliche Token-Spalten + Datenmigration
    if "api_token_id" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN api_token_id TEXT NOT NULL DEFAULT ''")
        con.execute("""
            UPDATE remotes SET api_token_id =
                CASE
                    WHEN pbs_token_id     != '' THEN pbs_token_id
                    WHEN pve_api_token_id != '' THEN pve_api_token_id
                    ELSE ''
                END
        """)
    if "api_token_secret" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN api_token_secret TEXT NOT NULL DEFAULT ''")
        con.execute("""
            UPDATE remotes SET api_token_secret =
                CASE
                    WHEN pbs_token_secret     != '' THEN pbs_token_secret
                    WHEN pve_api_token_secret != '' THEN pve_api_token_secret
                    ELSE ''
                END
        """)
    if "api_verify_ssl" not in existing:
        con.execute("ALTER TABLE remotes ADD COLUMN api_verify_ssl INTEGER NOT NULL DEFAULT 0")
        con.execute("""
            UPDATE remotes SET api_verify_ssl =
                CASE WHEN pbs_verify_ssl = 1 OR pve_verify_ssl = 1 THEN 1 ELSE 0 END
        """)

    con.commit()
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}

    # Backup der alten Tabelle + alte Spalten entfernen
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "api_token_id" in existing and "remotes_old" not in tables:
        con.execute("CREATE TABLE remotes_old AS SELECT * FROM remotes")

    for col in ("pve_api_token_id", "pve_api_token_secret", "pve_verify_ssl",
                "pbs_token_id", "pbs_token_secret", "pbs_verify_ssl"):
        if col in existing:
            try:
                con.execute(f"ALTER TABLE remotes DROP COLUMN {col}")
            except Exception:
                pass

    # description-Spalte entfernen
    existing = {row[1] for row in con.execute("PRAGMA table_info(remotes)").fetchall()}
    if "description" in existing:
        try:
            con.execute("ALTER TABLE remotes DROP COLUMN description")
        except Exception:
            pass

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
