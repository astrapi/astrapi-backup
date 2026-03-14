# modules/rsync.py
import subprocess

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.cmd import run_cmd, build_connection_string, is_local
from api.storage import load_config as _load_config
def _get_config(): return _load_config("rsync")


def preview(job_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_config().get(job_id) or _get_config().get(
        int(job_id) if str(job_id).isdigit() else job_id)
    if entry is None:
        return []

    source_host = entry["source_host"]
    source_path = entry["source_path"]
    target_host = entry["target_host"]
    target_path = entry["target_path"]
    connection  = build_connection_string(source_host)

    if is_local(target_host) or target_host == source_host:
        target = target_path
    else:
        target = f"{target_host}:{target_path}"

    cmd_parts = ["rsync", "-av", "--delete", "--itemize-changes", source_path, target]
    cmd_str   = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    return [{"label": "Rsync", "cmd": full_cmd}]


def run():
    for job_id, entry in _get_config().items():
        if not entry.get("enabled", False):
            continue
        run_single(job_id, entry)


def run_single(job_id, entry=None):
    if entry is None:
        entry = _get_config().get(job_id) or _get_config().get(
            int(job_id) if str(job_id).isdigit() else job_id)
    if entry is None:
        log("ERROR", f"Rsync-Eintrag '{job_id}' nicht gefunden")
        return
    set_log_context("rsync", job_id)
    try:
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' gestartet ===")
        hosts = [h for h in {entry.get("source_host"), entry.get("target_host")}
                 if h and not is_local(h)]
        if not require_hosts(hosts):
            return
        _rsync(entry)
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' abgeschlossen ===")
    finally:
        clear_log_context()


def _rsync(entry):
    source_host = entry["source_host"]
    source_path = entry["source_path"]
    target_host = entry["target_host"]
    target_path = entry["target_path"]

    if not source_path or not source_path.strip():
        log("ERROR", "Rsync abgebrochen: source_path ist leer (--delete würde Ziel löschen).")
        return
    if not target_path or not target_path.strip():
        log("ERROR", "Rsync abgebrochen: target_path ist leer.")
        return

    # rsync wird immer auf dem Source-Host ausgeführt
    connection = build_connection_string(source_host)

    # Ziel: lokal, gleicher Host wie Source, oder remote
    if is_local(target_host) or target_host == source_host:
        target = target_path
    else:
        target = f"{target_host}:{target_path}"

    cmd = ["rsync", "-av", "--delete", "--itemize-changes", source_path, target]

    try:
        run_cmd(cmd, connection)
        log("INFO", "Rsync erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Rsync fehlgeschlagen:")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
