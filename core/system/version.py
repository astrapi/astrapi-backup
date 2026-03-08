# core/system/version.py
"""Liest die aktuelle App-Version aus dem nächsten Git-Tag.

Format: JAHR.MONAT.RELEASE  (z.B. 26.3.1)
Fallback: übergebener Default-Wert.
"""
import subprocess
import time
from pathlib import Path

_cache: dict = {"val": None, "ts": 0.0, "root": None, "default": "—"}
_TTL = 30.0


def get_version(project_root: Path | None = None, default: str = "—") -> str:
    """Gibt den letzten Git-Tag zurück (z.B. '26.3.1').

    project_root: Verzeichnis innerhalb des Git-Repos (None → CWD).
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=str(project_root) if project_root else None,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return default


def get_version_cached(project_root: Path | None = None, default: str = "—") -> str:
    """Wie get_version(), aber mit 30-Sekunden-Cache (kein Subprocess pro Request)."""
    now = time.monotonic()
    if (
        _cache["val"] is None
        or now - _cache["ts"] > _TTL
        or _cache["root"] != project_root
        or _cache["default"] != default
    ):
        _cache["val"]     = get_version(project_root, default)
        _cache["ts"]      = now
        _cache["root"]    = project_root
        _cache["default"] = default
    return _cache["val"]
