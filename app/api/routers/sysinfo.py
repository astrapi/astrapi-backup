# api/routers/sysinfo.py
# Systeminfo-Seite: CPU/RAM/Disk, Versionen, systemd Status, Netzwerk, backupctl-Infos

import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.templates import templates

router = APIRouter(tags=["sysinfo"])

_START_TIME = time.time()


def _run(cmd: list, timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _borg_version() -> str:
    borg_paths = [
        "/var/lib/backupadm/.venv/bin/borg",
        "/usr/local/bin/borg",
        "/usr/bin/borg",
    ]
    for p in borg_paths:
        if Path(p).exists():
            v = _run([p, "--version"])
            return v.replace("borg ", "") if v else "?"
    v = _run(["borg", "--version"])
    return v.replace("borg ", "") if v else "nicht gefunden"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _systemd_service(name: str) -> dict:
    """Fragt systemd-Service-Status ab."""
    status = _run(["systemctl", "is-active", name])
    enabled = _run(["systemctl", "is-enabled", name])
    # Kurze Beschreibung
    desc = ""
    out = _run(["systemctl", "show", name, "--property=Description"])
    if "=" in out:
        desc = out.split("=", 1)[1]
    return {
        "name":    name,
        "active":  status,
        "enabled": enabled,
        "desc":    desc,
        "ok":      status == "active",
    }


def _disk_usage() -> list:
    """Alle gemounteten Dateisysteme (echte Partitionen, kein tmpfs etc.)."""
    disks = []
    for part in psutil.disk_partitions():
        if part.fstype in ("tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device":     part.device,
                "mountpoint": part.mountpoint,
                "fstype":     part.fstype,
                "total":      usage.total,
                "used":       usage.used,
                "free":       usage.free,
                "percent":    usage.percent,
                "total_fmt":  _fmt_size(usage.total),
                "used_fmt":   _fmt_size(usage.used),
                "free_fmt":   _fmt_size(usage.free),
            })
        except (PermissionError, OSError):
            continue
    return disks


def _net_interfaces() -> list:
    """Netzwerk-Interfaces mit IP-Adressen."""
    ifaces = []
    stats   = psutil.net_if_stats()
    addrs   = psutil.net_if_addrs()
    for name, addr_list in addrs.items():
        if name == "lo":
            continue
        ipv4 = [a.address for a in addr_list if a.family.name == "AF_INET"]
        ipv6 = [a.address.split("%")[0] for a in addr_list if a.family.name == "AF_INET6"]
        mac  = next((a.address for a in addr_list if a.family.name in ("AF_LINK", "AF_PACKET")), "")
        st   = stats.get(name)
        ifaces.append({
            "name":  name,
            "ipv4":  ipv4,
            "ipv6":  ipv6,
            "mac":   mac,
            "up":    st.isup if st else False,
            "speed": f"{st.speed} Mbit/s" if st and st.speed else "—",
        })
    return ifaces


def _fmt_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if not parts: parts.append(f"{s}s")
    return " ".join(parts)


def _db_size() -> str:
    """Größe der backupctl SQLite-Datenbank."""
    # DB-Pfad aus storage.py ableiten
    try:
        from api.storage import DB_PATH
        if Path(DB_PATH).exists():
            return _fmt_size(Path(DB_PATH).stat().st_size)
    except Exception:
        pass
    # Fallback: suche backupctl.db
    for candidate in [
        Path(__file__).parents[2] / "data" / "backupctl.db",
        Path("/var/lib/backupadm/backupctl.db"),
        Path("/tmp/backupctl.db"),
    ]:
        if candidate.exists():
            return _fmt_size(candidate.stat().st_size)
    return "—"


def _secret_key_info() -> tuple[str, bool]:
    """Pfad und Status des Fernet-Keys."""
    try:
        from helpers.secrets import key_location
        path = key_location()
        ok = Path(path).exists()
        return path, ok
    except Exception:
        return "unbekannt", False


def _collect_all() -> dict:
    """Alle Systemdaten sammeln."""
    cpu_percent  = psutil.cpu_percent(interval=0.5)
    cpu_count    = psutil.cpu_count()
    cpu_freq     = psutil.cpu_freq()
    mem          = psutil.virtual_memory()
    swap         = psutil.swap_memory()
    boot_time    = psutil.boot_time()
    sys_uptime   = time.time() - boot_time
    app_uptime   = time.time() - _START_TIME

    # Hostname
    hostname = _run(["hostname", "-f"]) or _run(["hostname"]) or "?"

    # Kernel
    kernel = _run(["uname", "-r"])

    # OS
    try:
        import platform
        os_name = platform.platform()
    except Exception:
        os_name = "?"

    # CPU-Modell
    cpu_model = ""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except Exception:
        pass

    # Services
    services = [
        _systemd_service("backupctl"),
        _systemd_service("borgbackup"),
    ]

    # backupctl-Version aus settings.py
    backupctl_version = "?"
    try:
        from app import settings as _s
        backupctl_version = getattr(_s, "APP_VERSION", "?")
    except Exception:
        try:
            import importlib.util, sys as _sys
            p = Path(__file__).parents[2] / "settings.py"
            spec = importlib.util.spec_from_file_location("_app_settings", p)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            backupctl_version = getattr(mod, "APP_VERSION", "?")
        except Exception:
            pass

    return {
        # CPU
        "cpu_percent":  cpu_percent,
        "cpu_count":    cpu_count,
        "cpu_freq":     f"{cpu_freq.current:.0f} MHz" if cpu_freq else "—",
        "cpu_model":    cpu_model,
        # RAM
        "mem_total":    _fmt_size(mem.total),
        "mem_used":     _fmt_size(mem.used),
        "mem_free":     _fmt_size(mem.available),
        "mem_percent":  mem.percent,
        # Swap
        "swap_total":   _fmt_size(swap.total),
        "swap_used":    _fmt_size(swap.used),
        "swap_percent": swap.percent,
        # System
        "hostname":     hostname,
        "kernel":       kernel,
        "os_name":      os_name,
        "sys_uptime":   _fmt_uptime(sys_uptime),
        "app_uptime":   _fmt_uptime(app_uptime),
        # Disk
        "disks":        _disk_usage(),
        # Netzwerk
        "interfaces":   _net_interfaces(),
        # Versionen
        "borg_version":       _borg_version(),
        "python_version":     _python_version(),
        "backupctl_version":  backupctl_version,
        "psutil_version":     psutil.__version__,
        # Services
        "services":     services,
        # DB & Secrets
        "db_size":         _db_size(),
        "secret_key_path": _secret_key_info()[0],
        "secret_key_ok":   _secret_key_info()[1],
        # Zeitstempel
        "collected_at": datetime.now().strftime("%H:%M:%S"),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tab", response_class=HTMLResponse)
def sysinfo_tab(request: Request):
    data = _collect_all()
    return templates.TemplateResponse("partials/sysinfo/tab.html", {
        "request": request,
        **data,
    })


@router.get("/refresh", response_class=HTMLResponse)
def sysinfo_refresh(request: Request):
    """Nur die Metriken-Karten aktualisieren (HTMX-Target)."""
    data = _collect_all()
    return templates.TemplateResponse("partials/sysinfo/metrics.html", {
        "request": request,
        **data,
    })
