"""backupctl._paths – zentrale Laufzeit-Pfade.

work_dir() liest BACKUPCTL_WORK_DIR (gesetzt von --work-dir).
Ist die Variable nicht gesetzt, wird ein RuntimeError ausgelöst.
"""
import os
from pathlib import Path


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def work_dir() -> Path:
    val = os.environ.get("BACKUPCTL_WORK_DIR", "").strip()
    if not val:
        raise RuntimeError(
            "BACKUPCTL_WORK_DIR nicht gesetzt. "
            "backupctl mit --work-dir /pfad/zum/verzeichnis starten."
        )
    return Path(val)


def db_path() -> Path:
    return work_dir() / "data" / "app.db"


def log_dir() -> Path:
    return work_dir() / "logs"
