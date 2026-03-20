"""backupctl-spezifische Konfiguration des Core-Sysinfo-Moduls."""
import subprocess
from pathlib import Path

from core.modules.sysinfo import module  # noqa: F401  – wird von der Registry erwartet
from core.modules.sysinfo.engine import configure


def _run(cmd: list) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def _borg_version() -> str:
    for p in ["/var/lib/backupadm/.venv/bin/borg", "/usr/local/bin/borg", "/usr/bin/borg"]:
        if Path(p).exists():
            v = _run([p, "--version"])
            return v.replace("borg ", "") if v else "?"
    v = _run(["borg", "--version"])
    return v.replace("borg ", "") if v else "nicht gefunden"


def _app_version() -> str:
    try:
        import yaml as _yaml
        cfg = Path(__file__).parents[1] / "config.yaml"
        if cfg.exists():
            with open(cfg, encoding="utf-8") as f:
                return str((_yaml.safe_load(f) or {}).get("app", {}).get("version", "?"))
    except Exception:
        pass
    return "?"


def _db_size() -> str:
    from core.system.format import fmt_bytes
    try:
        from api.storage import DB_PATH
        p = Path(DB_PATH)
        if p.exists():
            return fmt_bytes(p.stat().st_size)
    except Exception:
        pass
    for candidate in [
        Path(__file__).parents[1] / "data" / "app.db",
        Path("/var/lib/backupadm/app.db"),
    ]:
        if candidate.exists():
            return fmt_bytes(candidate.stat().st_size)
    return "—"


def _fernet_key() -> str:
    try:
        from core.system.secrets import key_location
        path = key_location()
        ok = Path(path).exists()
        return ("✔ " if ok else "✗ fehlt  ") + str(path)
    except Exception:
        return "—"


def _extra_info() -> dict:
    return {
        "backupctl":  f"v{_app_version()}",
        "Borg":       _borg_version(),
        "DB":         _db_size(),
        "Fernet-Key": _fernet_key(),
    }


configure(
    services=["backupctl", "borgbackup"],
    extra_info_fn=_extra_info,
)
