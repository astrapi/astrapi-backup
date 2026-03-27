"""
tests/unit/conftest.py

Fixtures für Unit-Tests:
- Jeder Test bekommt eine frische, temporäre SQLite-DB
- Jeder Test bekommt eine isolierte Scheduler-Instanz (kein Singleton)
- Externe Abhängigkeiten (notify, activity_log) werden durch Stubs ersetzt
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tests brauchen kein echtes work-dir – DB wird per fresh_db-Fixture ersetzt
os.environ.setdefault("BACKUPCTL_WORK_DIR", "/tmp/backupctl-test")


# ── Datenbank ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Konfiguriert eine frische SQLite-DB für jeden Test und räumt danach auf."""
    import astrapi.core.system.db as db
    from astrapi.core.ui.storage import SqliteStorage

    # Vorhandene Thread-lokale Verbindung schließen
    if getattr(db._local, "conn", None):
        try:
            db._local.conn.close()
        except Exception:
            pass
        del db._local.conn

    db.configure(tmp_path / "test.db")
    SqliteStorage._DATA_DIR = None  # YAML-Migration deaktivieren

    yield

    # Aufräumen
    if getattr(db._local, "conn", None):
        try:
            db._local.conn.close()
        except Exception:
            pass
        del db._local.conn

    db._db_path = None
    SqliteStorage._DATA_DIR = None


# ── Scheduler ─────────────────────────────────────────────────────────────

@pytest.fixture
def scheduler():
    """Frische, isolierte Scheduler-Instanz (nicht der Modul-Singleton)."""
    from astrapi.core.modules.scheduler.engine import Scheduler
    sch = Scheduler()
    yield sch
    sch.reset()
