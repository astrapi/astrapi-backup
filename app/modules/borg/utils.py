# app/modules/borg/utils.py
"""Gemeinsame Borg-Hilfsfunktionen für jobs.py und api.py."""
import os

from core.system.secrets import get_secret
from core.ui.settings_registry import get_module as _get_module_setting

_BORG_DEFAULT = "/var/lib/backupadm/.venv/bin/borg"


def borg_bin() -> str:
    return _get_module_setting("borg", "borg_bin", _BORG_DEFAULT) or _BORG_DEFAULT


def borg_env() -> dict:
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = _get_module_setting("borg", "passphrase", "") or get_secret("BORG_PASSPHRASE")
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    return env
