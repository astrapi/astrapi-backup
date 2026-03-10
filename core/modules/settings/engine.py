"""
core/modules/settings/engine.py – Framework-Status für die Einstellungsseite

Projekte konfigurieren den Health-Check:

    from core.modules.settings.engine import configure
    configure(health_fn=my_check_fn)   # () -> (ok: bool, details: dict)
"""

import os
import time

_START_TIME: float = time.time()
_health_fn = None


def configure(health_fn=None) -> None:
    """Registriert eine Health-Check-Funktion.

    health_fn: callable () -> (ok: bool, details: dict)
    """
    global _health_fn
    if health_fn is not None:
        _health_fn = health_fn


def get_status() -> dict:
    """Gibt den aktuellen Framework-Status zurück."""
    uptime_s = int(time.time() - _START_TIME)
    h, rem   = divmod(uptime_s, 3600)
    m, s     = divmod(rem, 60)
    uptime_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

    systemd_active = bool(os.environ.get("NOTIFY_SOCKET"))

    health_ok      = None
    health_details = {}
    if _health_fn is not None:
        try:
            health_ok, health_details = _health_fn()
        except Exception:
            health_ok = False

    return {
        "uptime_s":       uptime_s,
        "uptime":         uptime_str,
        "systemd_active": systemd_active,
        "health_ok":      health_ok,
        "health_details": health_details,
    }
