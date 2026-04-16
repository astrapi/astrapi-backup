# app/modules/borg/utils.py
"""Gemeinsame Borg-Hilfsfunktionen für jobs.py und api.py."""
import os
import shutil

from astrapi.core.system.secrets import get_secret_safe
from astrapi.core.ui.settings_registry import get_module as _get_module_setting

_BORG_REMOTE_DEFAULT = "/var/lib/backupadm/.venv/bin/borg"


def borg_bin() -> str:
    """Globaler Remote-Default aus den Borg-Einstellungen."""
    return _get_module_setting("borg", "borg_bin", _BORG_REMOTE_DEFAULT) or _BORG_REMOTE_DEFAULT


def borg_bin_local() -> str:
    """Borg-Pfad für lokale Ausführung. Fallback: which borg."""
    configured = _get_module_setting("borg", "borg_bin_local", "") or ""
    if configured:
        return configured
    found = shutil.which("borg")
    return found if found else _BORG_REMOTE_DEFAULT


def borg_bin_for(remote_id) -> str:
    """
    Gibt den borg-Pfad für eine bestimmte Quelle zurück.

    Reihenfolge:
      - remote_id == None oder "local" → borg_bin_local()
      - Remote-Gerät hat borg_bin gesetzt → remote-spezifischer Pfad
      - sonst → globaler Remote-Default aus Einstellungen
    """
    if remote_id is None or str(remote_id) == "local":
        return borg_bin_local()
    try:
        from astrapi_backup.modules.remotes.engine import get_remote
        remote = get_remote(remote_id)
        if remote and remote.get("borg_bin"):
            return remote["borg_bin"]
    except Exception:
        pass
    return borg_bin()


def borg_env() -> dict:
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret_safe("module.borg.passphrase", "")
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env
