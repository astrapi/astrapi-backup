"""backupctl._paths – zentrale Laufzeit-Pfade.

Priorität für data_dir():
  1. Umgebungsvariable BACKUPCTL_DATA_DIR
  2. /var/lib/backupctl  (Produktion, wenn beschreibbar)
  3. ./              (Entwicklungs-Fallback, cwd)
     → DB:   ./data/app.db
     → Logs: ./logs/
"""
import os
from pathlib import Path


def package_dir() -> Path:
    """Pfad zum installierten Package – für app.yaml, Templates, Modul-YAMLs."""
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    env = os.environ.get("BACKUPCTL_DATA_DIR", "").strip()
    if env:
        return Path(env)
    prod = Path("/var/lib/backupctl")
    if prod.exists() and os.access(prod, os.W_OK):
        return prod
    return Path.cwd()


def db_path() -> Path:
    return data_dir() / "data" / "app.db"


def log_dir() -> Path:
    return data_dir() / "logs"
