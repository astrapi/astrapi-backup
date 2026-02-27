# helpers/logger.py
import threading
from datetime import datetime, timedelta
from pathlib import Path

LOG_ROOT = Path("logs")
_lock = threading.Lock()

# ── Haupt-Log-Kontext (pro Thread) ───────────────────────────────
_context     = threading.local()

# ── Tee-Kontext: alle log()-Zeilen werden zusätzlich hierhin gespiegelt ──────
_tee_context = threading.local()


# ── Pfad-Hilfsfunktion ────────────────────────────────────────────

def log_path(module: str, item_id: str, date: datetime = None) -> Path:
    d = date or datetime.now()
    return LOG_ROOT / module / str(item_id) / f"{d.strftime('%Y-%m-%d')}.log"


def _write(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _cleanup_old_logs(module: str, item_id: str) -> None:
    cutoff = datetime.now() - timedelta(days=14)
    folder = LOG_ROOT / module / str(item_id)
    if not folder.exists():
        return
    for f in folder.glob("*.log"):
        try:
            if datetime.strptime(f.stem, "%Y-%m-%d") < cutoff:
                f.unlink()
        except ValueError:
            pass


# ── Kontext-Verwaltung ────────────────────────────────────────────

def set_log_context(module: str, item_id: str) -> None:
    _context.module  = module
    _context.item_id = str(item_id)
    _cleanup_old_logs(module, item_id)


def clear_log_context() -> None:
    _context.module  = None
    _context.item_id = None


def get_log_context():
    return getattr(_context, "module", None), getattr(_context, "item_id", None)


def set_tee_context(module: str, item_id: str) -> None:
    """Zusätzlicher Kontext – jede log()-Zeile wird auch dorthin gespiegelt."""
    _tee_context.module  = module
    _tee_context.item_id = str(item_id)
    _cleanup_old_logs(module, item_id)


def clear_tee_context() -> None:
    _tee_context.module  = None
    _tee_context.item_id = None


# ── Logging ───────────────────────────────────────────────────────

def log(*args) -> None:
    if len(args) == 1:
        level, message = "INFO", args[0]
    elif len(args) == 2:
        level, message = args[0].upper(), args[1]
    else:
        raise ValueError("log() erwartet 1 oder 2 Argumente")

    now  = datetime.now()
    line = f"{now.strftime('%H:%M:%S')} {level}: {message}"
    print(line)

    # Haupt-Kontext
    module, item_id = get_log_context()
    if module and item_id:
        _write(log_path(module, item_id, now), line)

    # Tee-Kontext (nur wenn abweichend)
    tee_mod = getattr(_tee_context, "module", None)
    tee_id  = getattr(_tee_context, "item_id", None)
    if tee_mod and tee_id and (tee_mod, tee_id) != (module, item_id):
        _write(log_path(tee_mod, tee_id, now), line)


# ── Lesen ─────────────────────────────────────────────────────────

def get_log_dates(module: str, item_id: str) -> list:
    folder = LOG_ROOT / module / str(item_id)
    if not folder.exists():
        return []
    return sorted([f.stem for f in folder.glob("*.log")], reverse=True)


def read_log(module: str, item_id: str, date: str) -> list:
    path = LOG_ROOT / module / str(item_id) / f"{date}.log"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [l.rstrip() for l in f.readlines()]


def get_all_errors(days: int = 14) -> list:
    cutoff  = datetime.now() - timedelta(days=days)
    results = []
    if not LOG_ROOT.exists():
        return []

    for module_dir in sorted(LOG_ROOT.iterdir()):
        if not module_dir.is_dir():
            continue
        for item_dir in sorted(module_dir.iterdir()):
            if not item_dir.is_dir():
                continue
            # __run__ und __debug__ sind Gesamt-Logs, keine Einzeleinträge
            if item_dir.name.startswith("__"):
                continue

            description = _get_description(module_dir.name, item_dir.name)

            for log_file in sorted(item_dir.glob("*.log"), reverse=True):
                try:
                    if datetime.strptime(log_file.stem, "%Y-%m-%d") < cutoff:
                        continue
                except ValueError:
                    continue

                with log_file.open("r", encoding="utf-8") as f:
                    all_lines = [l.rstrip() for l in f.readlines()]

                i = 0
                while i < len(all_lines):
                    line = all_lines[i]
                    if "WARNING:" in line:
                        group = [line]
                        j = i + 1
                        while j < len(all_lines) and "ERROR:" in all_lines[j]:
                            group.append(all_lines[j])
                            j += 1
                        time_str = line[:8] if len(line) >= 8 else ""
                        results.append({
                            "date": log_file.stem,
                            "time": time_str,
                            "module": module_dir.name,
                            "item_id": item_dir.name,
                            "description": description,
                            "lines": group,
                        })
                        i = j
                    else:
                        i += 1

    results.sort(key=lambda x: (x["date"], x["time"]), reverse=True)
    return results


def _get_description(module: str, item_id: str) -> str:
    try:
        from api.storage import get_item
        item = get_item(module, item_id)
        if item and item.get("description"):
            return item["description"]
    except Exception:
        pass
    return item_id


def get_ntfy_logs(level: str) -> str:
    module, item_id = get_log_context()
    if not module or not item_id:
        return ""
    lines = read_log(module, item_id, datetime.now().strftime("%Y-%m-%d"))
    return "\n".join(l for l in lines if f"{level}:" in l)
