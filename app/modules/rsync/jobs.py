import subprocess

from core.system.logger import log, log_context
from core.system.reachability import require_hosts
from core.system.cmd import run_cmd, build_connection_string, is_local
from api.storage import load_config as _load_config
from core.ui.settings_registry import get_module as _get_module_setting, get as _get_global_setting

def _get_config(): return _load_config("rsync")

def preview(job_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_config().get(job_id) or _get_config().get(
        int(job_id) if str(job_id).isdigit() else job_id)
    if entry is None:
        return []

    source_host = entry.get("source_host", "")
    source_path = entry.get("source_path", "")
    target_host = entry.get("target_host", "")
    target_path = entry.get("target_path", "")
    if not source_host or not source_path or not target_host or not target_path:
        return []
    connection  = build_connection_string(source_host)

    if is_local(target_host) or target_host == source_host:
        target = target_path
    else:
        target = f"{target_host}:{target_path}"

    # SSH ConnectTimeout
    ssh_connect_timeout = _get_global_setting("ssh_connect_timeout", 10)

    # Rsync Flags
    rsync_delete = _get_module_setting("rsync", "rsync_delete", True)
    rsync_compress = _get_module_setting("rsync", "rsync_compress", False)
    cmd_parts = ["rsync", "-av", "--itemize-changes", source_path, target]
    if rsync_delete:
        cmd_parts.append("--delete")
    if rsync_compress:
        cmd_parts.append("-z")
    cmd_str   = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout={ssh_connect_timeout} {connection} '{cmd_str}'"

    return [{"label": "Rsync", "cmd": full_cmd}]

def run():
    from core.modules.scheduler.job_runner import run_all
    run_all("rsync", _get_config(), run_single)

def run_single(job_id, entry=None):
    if entry is None:
        entry = _get_config().get(job_id) or _get_config().get(
            int(job_id) if str(job_id).isdigit() else job_id)
    if entry is None:
        log("ERROR", f"Rsync-Eintrag '{job_id}' nicht gefunden")
        return
    with log_context("rsync", job_id):
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' gestartet ===")
        hosts = [h for h in {entry.get("source_host"), entry.get("target_host")}
                 if h and not is_local(h)]
        if not require_hosts(hosts):
            return
        _rsync(entry)
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' abgeschlossen ===")


def _rsync(entry):
    source_host = entry.get("source_host", "")
    source_path = entry.get("source_path", "")
    target_host = entry.get("target_host", "")
    target_path = entry.get("target_path", "")

    if not source_host or not target_host:
        log("ERROR", "Rsync abgebrochen: source_host oder target_host fehlt.")
        return
    if not source_path or not source_path.strip():
        log("ERROR", "Rsync abgebrochen: source_path ist leer (--delete würde Ziel löschen).")
        return
    if not target_path or not target_path.strip():
        log("ERROR", "Rsync abgebrochen: target_path ist leer.")
        return

    # rsync wird immer auf dem Source-Host ausgeführt
    connection = build_connection_string(source_host)

    # SSH ConnectTimeout
    ssh_connect_timeout = _get_global_setting("ssh_connect_timeout", 10)

    # Rsync Flags
    rsync_delete = _get_module_setting("rsync", "rsync_delete", True)
    rsync_compress = _get_module_setting("rsync", "rsync_compress", False)

    # Ziel: lokal, gleicher Host wie Source, oder remote
    if is_local(target_host) or target_host == source_host:
        target = target_path
    else:
        target = f"{target_host}:{target_path}"

    cmd = ["rsync", "-av", "--itemize-changes", source_path, target]
    if rsync_delete:
        cmd.append("--delete")
    if rsync_compress:
        cmd.append("-z")

    try:
        run_cmd(cmd, connection, ssh_connect_timeout=ssh_connect_timeout)
        log("INFO", "Rsync erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Rsync fehlgeschlagen:")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")

