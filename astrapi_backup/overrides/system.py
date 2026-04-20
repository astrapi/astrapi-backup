"""astrapi-backup-spezifische Konfiguration des Core-Sysinfo-Moduls."""
import subprocess
from pathlib import Path

from astrapi_core.modules.system import module  
from astrapi_core.modules.system.engine import configure

from astrapi_backup._paths import package_dir as _package_dir, db_path as _db_path


def _run(cmd: list) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def _borg_version() -> str:
    try:
        from astrapi_backup.modules.borg.utils import borg_bin_local
        p = borg_bin_local()
    except Exception:
        p = "borg"
    v = _run([p, "--version"])
    return v.replace("borg ", "") if v else "nicht gefunden"


def _read_version_yaml(path: Path) -> str:
    try:
        import yaml as _yaml
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return str((_yaml.safe_load(f) or {}).get("version", "?"))
    except Exception:
        pass
    return "?"

def _db_size() -> str:
    from astrapi_core.system.format import fmt_bytes
    p = _db_path()
    if p.exists():
        return fmt_bytes(p.stat().st_size)
    return "—"

def _extra_info() -> dict:
    return {
        "Borg":      _borg_version(),
        "DB":        _db_size(),
    }

def _discover_services() -> list[str]:
    try:
        import yaml as _yaml
        app_yaml = _package_dir() / "app.yaml"
        name = str((_yaml.safe_load(app_yaml.read_text()) or {}).get("name", ""))
        if not name:
            return []
        out = _run(["systemctl", "list-units", "--all", "--no-legend", "--plain",
                    "--type=service", f"{name}*"])
        return [line.split()[0].removesuffix(".service")
                for line in out.splitlines() if line.strip()]
    except Exception:
        return []


def _update_packages():
    from astrapi_core.modules.system.updater import get_packages_with_versions
    return get_packages_with_versions()


configure(
    services=_discover_services(),
    extra_info_fn=_extra_info,
    update_packages_fn=_update_packages,
)
