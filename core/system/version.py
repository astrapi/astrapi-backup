"""core/system/version.py – Liest Versionsnummern aus version.yaml-Dateien.

Format: JAHR.MONAT.NUMMER  (z.B. 26.3.2)
"""
from pathlib import Path


def _read_yaml_version(yaml_path: Path, default: str = "—") -> str:
    """Liest 'version' aus einer version.yaml. Gibt default zurück wenn nicht vorhanden."""
    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return str(data.get("version", default))
    except Exception:
        return default


def get_app_version(app_root: Path, default: str = "—") -> str:
    """Liest die App-Version aus <app_root>/version.yaml."""
    return _read_yaml_version(app_root / "version.yaml", default)


def get_core_version(core_root: Path, default: str = "—") -> str:
    """Liest die Core-Version aus <core_root>/version.yaml."""
    return _read_yaml_version(core_root / "version.yaml", default)
