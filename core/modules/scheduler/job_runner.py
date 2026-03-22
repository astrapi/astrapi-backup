# core/modules/scheduler/job_runner.py
"""Hilfsfunktion zum Ausführen eines einzelnen Jobs mit eigenem Activity-Log-Eintrag.

Wird von den Bulk-Run-Funktionen der Module verwendet (run(), run_by_type()),
damit Scheduler-ausgelöste Läufe genauso im Activity Log erscheinen wie
manuell über die UI gestartete Jobs.
"""
import time

from core.system.activity_log import history_start, history_finish, get_log_lines
from core.system.logger import get_active_log_id, set_active_log_id, clear_active_log_id, log


def _notify(module: str, description: str, status: str, duration: int) -> None:
    try:
        from core.modules.notify import engine as _ne
        if status == "ok":
            _ne.send(
                title   = f"Job abgeschlossen: {description}",
                message = f"Dauer: {duration}s",
                event   = _ne.SUCCESS,
                source  = module,
                tags    = [module],
            )
        elif status == "warning":
            _ne.send(
                title   = f"Job mit Warnung: {description}",
                message = f"Dauer: {duration}s",
                event   = _ne.WARNING,
                source  = module,
                tags    = [module],
            )
        else:
            _ne.send(
                title   = f"Job fehlgeschlagen: {description}",
                message = f"Dauer: {duration}s",
                event   = _ne.ERROR,
                source  = module,
                tags    = [module],
            )
    except Exception:
        pass


def run_all(module: str, config: dict, run_fn, desc_fn=None) -> None:
    """Führt alle aktivierten Einträge aus config aus.

    run_fn(item_id, entry) wird pro Eintrag aufgerufen.
    desc_fn(item_id, entry) → str kann optional eine abweichende Beschreibung liefern.
    Sammelt Fehler und wirft am Ende eine RuntimeError wenn welche aufgetreten sind.
    """
    errors = []
    for item_id, entry in config.items():
        if not entry.get("enabled", False):
            continue
        desc = desc_fn(item_id, entry) if desc_fn else entry.get("description", str(item_id))
        try:
            run_logged(module, item_id, desc, lambda iid=item_id, e=entry: run_fn(iid, e))
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError("; ".join(errors))


def run_logged(module: str, item_id: str, description: str, fn) -> None:
    """Führt fn() aus und erstellt einen eigenen Activity-Log-Eintrag dafür.

    Stellt den vorherigen Log-Kontext (z.B. den übergeordneten Scheduler-Eintrag)
    nach Abschluss wieder her. Wirft bei Fehler eine Exception, damit der
    Scheduler korrekt "fehlgeschlagen" melden kann.
    """
    parent_id = get_active_log_id()
    hist_id   = history_start(module, str(item_id), description, "run")
    set_active_log_id(hist_id)
    # Startbenachrichtigung
    try:
        from core.modules.notify import engine as _ne
        _ne.send(
            title   = f"Job gestartet: {description}",
            message = "",
            event   = _ne.INFO,
            source  = module,
            tags    = [module],
        )
    except Exception:
        pass
    status = "ok"
    t0     = time.time()
    try:
        fn()
    except Exception:
        status = "error"
    finally:
        duration = int(time.time() - t0)
        if status == "ok":
            levels = {r["level"] for r in get_log_lines(hist_id)}
            if "ERROR" in levels:
                status = "error"
            elif "WARNING" in levels:
                status = "warning"
        history_finish(hist_id, status, duration)
        # Eltern-Kontext wiederherstellen
        if parent_id is not None:
            set_active_log_id(parent_id)
        else:
            clear_active_log_id()
        # Kurze Statuszeile in den übergeordneten Kontext (z.B. Scheduler-Eintrag)
        if get_active_log_id() is not None:
            icon = "✓" if status == "ok" else ("⚠" if status == "warning" else "✗")
            lvl  = "INFO" if status == "ok" else ("WARNING" if status == "warning" else "ERROR")
            log(lvl, f"{icon} {description}: {status} ({duration}s)")
        # Benachrichtigung senden – vor dem möglichen raise, damit sie VOR der
        # Scheduler-Abschlussbenachrichtigung ankommt
        _notify(module, description, status, duration)

    # Nach dem finally: bei Fehler Exception werfen, damit der Scheduler den
    # Schritt als fehlgeschlagen wertet und seine eigene Benachrichtigung
    # entsprechend sendet (fehlgeschlagen statt abgeschlossen)
    if status == "error":
        raise RuntimeError(f"{description}: fehlgeschlagen")
