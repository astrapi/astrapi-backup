# helpers/secrets.py
#
# Alle Credentials landen Fernet-verschlüsselt in SQLite.
#
# Trennung von Key und Daten (Threat-Model: DB-Datei-Diebstahl via Backup):
#
#   DB   → app/data/backupctl.db        (landet in Borg-Backups → verschlüsselt)
#   Key  → /var/lib/backupadm/secret.key  (AUSSERHALB des Backup-Pfads, chmod 600)
#
# Ein Backup-Dump der DB ist ohne den Key wertlos.
# Der Key allein ist ohne die DB wertlos.
# Beide sind nie im selben Backup.

import os
from pathlib import Path
from cryptography.fernet import Fernet

# Key liegt bewusst außerhalb des App-Verzeichnisses.
# Fallback für Entwicklungsumgebungen wo /var/lib/backupadm/ nicht existiert.
_KEY_PATH = Path("/var/lib/backupadm/secret.key")
_KEY_PATH_DEV = Path(__file__).resolve().parent.parent / "config" / "secret.key"


def _key_path() -> Path:
    """Produktiv: /var/lib/backupadm/secret.key – Dev-Fallback: config/secret.key"""
    # Produktivpfad nutzen wenn das Verzeichnis existiert oder angelegt werden kann
    try:
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        return _KEY_PATH
    except (PermissionError, OSError):
        # Entwicklungsumgebung ohne /var/lib/backupadm
        _KEY_PATH_DEV.parent.mkdir(parents=True, exist_ok=True)
        return _KEY_PATH_DEV


def _fernet() -> Fernet:
    """Lädt oder erzeugt den Fernet-Key."""
    path = _key_path()
    if not path.exists():
        key = Fernet.generate_key()
        path.write_bytes(key)
        path.chmod(0o600)
    return Fernet(path.read_bytes())


def _db_set(key: str, value: str) -> None:
    from api.storage import set_setting
    token = _fernet().encrypt(value.encode()).decode()
    set_setting(f"__secret__{key}", token)
    os.environ[key] = value   # Laufzeit-Cache für os.environ-Leser


def _db_get(key: str, default: str = "") -> str:
    from api.storage import get_setting
    token = get_setting(f"__secret__{key}", "")
    if not token:
        return default
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return default


# ── Öffentliche API ───────────────────────────────────────────────────────────

def set_secret(key: str, value: str) -> None:
    """Speichert einen Credential-Wert Fernet-verschlüsselt in SQLite."""
    _db_set(key, value)


def get_secret(key: str) -> str:
    """Gibt einen Credential-Wert zurück – wirft RuntimeError wenn nicht gesetzt."""
    val = _db_get(key) or os.environ.get(key, "")
    if not val:
        raise RuntimeError(f"Secret '{key}' ist nicht gesetzt!")
    return val


def get_secret_safe(key: str, default: str = "") -> str:
    """Gibt einen Credential-Wert zurück, oder default wenn nicht gesetzt."""
    return _db_get(key) or os.environ.get(key, default) or default


def get_all_secrets() -> dict:
    """Gibt alle gesetzten Secrets als Klartext-Dict zurück."""
    from api.storage import _conn, _init_settings
    _init_settings()
    rows = _conn().execute(
        "SELECT key, value FROM settings WHERE key LIKE '__secret__%'"
    ).fetchall()
    result = {}
    f = _fernet()
    for row in rows:
        env_key = row["key"].replace("__secret__", "", 1)
        try:
            result[env_key] = f.decrypt(row["value"].encode()).decode()
        except Exception:
            result[env_key] = ""
    return result


# ┌─────────────────────────────────────────────────────────────────┐
# │  MIGRATIONS-BLOCK – nach erfolgter Migration entfernbar         │
# │                                                                 │
# │  Sobald alle Instanzen einmal mit v72+ gestartet wurden und     │
# │  die secrets.env-Werte in der DB sind, kann dieser Block samt  │
# │  dem Aufruf in main.py und "python-dotenv" in requirements.txt │
# │  ersatzlos gelöscht werden.                                     │
# └─────────────────────────────────────────────────────────────────┘
def migrate_from_env_file() -> list[str]:
    """
    Einmalige Migration: liest secrets.env und importiert Werte in die DB.
    Läuft nur beim allerersten Start (Flag __migration_v72_done in DB).
    """
    from api.storage import get_setting, set_setting
    if get_setting("__migration_v72_done"):
        return []   # bereits migriert – sofort raus

    env_path = Path(__file__).resolve().parent.parent / "config" / "secrets.env"
    if not env_path.exists():
        set_setting("__migration_v72_done", "1")
        return []

    migrated = []
    try:
        from dotenv import dotenv_values   # python-dotenv (nur für Migration nötig)
        values = dotenv_values(str(env_path))
    except ImportError:
        # python-dotenv nicht installiert → manuelles Parsen
        values = {}
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip().strip('"\'')] = v.strip().strip('"\'')

    for key, val in values.items():
        if key and val and not _db_get(key):
            _db_set(key, val)
            migrated.append(key)

    set_setting("__migration_v72_done", "1")
    return migrated
# └── Ende Migrations-Block ─────────────────────────────────────────────────


def key_location() -> str:
    """Gibt den tatsächlich verwendeten Key-Pfad zurück (für Logging/Diagnose)."""
    return str(_key_path())
