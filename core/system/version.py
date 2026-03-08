# core/system/version.py
"""Liest die aktuelle App-Version aus dem nächsten Git-Tag.

Format: JAHR.MONAT.RELEASE  (z.B. 26.3.1)
Fallback: übergebener Default-Wert.
"""
import subprocess
from pathlib import Path


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
