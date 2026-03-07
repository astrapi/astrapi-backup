# modules/rsync.py
import subprocess

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.cmd import run_cmd, build_connection_string, is_local
from helpers.debug import is_debug

from api.storage import load_config as _load_config
def _get_config(): return _load_config("rsync")


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
    from helpers.debug import is_debug
    log_id = f"{job_id}_debug" if is_debug() else job_id
    set_log_context("rsync", log_id)
    try:
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' gestartet ===")
        if not is_debug():
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
