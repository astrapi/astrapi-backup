import subprocess

from astrapi.core.system.logger import log, log_context
from astrapi.core.system.reachability import require_hosts
from astrapi.core.system.cmd import run_cmd, build_connection_string, is_local
from astrapi_backup.api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item
from astrapi.core.ui.settings_registry import get_module as _get_module_setting, get as _get_global_setting

def _get_config(): return _load_config("rsync")


def _get_host_info(entry: dict, host_type: str = "source") -> tuple[str, str, int]:
    """
    Resolve host/ssh_user/ssh_port from Remote Device OR legacy fields.

    Tries:
    1. New way: {host_type}_remote_id → Remote Device
    2. Old way: {host_type}_host field
    """
    remote_id_key = f"{host_type}_remote_id"
    host_key = f"{host_type}_host"

    if remote_id_key in entry and entry[remote_id_key]:
        from astrapi_backup.modules.remotes.engine import get_remote_ssh
        try:
            return get_remote_ssh(entry[remote_id_key])
        except ValueError as e:
            log("ERROR", str(e))
            raise

    elif host_key in entry and entry[host_key]:
        host = entry[host_key]
        ssh_user = entry.get("ssh_user")
        return (host, ssh_user, 22)

    else:
        raise ValueError(
            f"Job missing: neither '{remote_id_key}' nor '{host_key}' configured"
        )


def preview(job_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), job_id)
    if entry is None:
        return []

    try:
        source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
    except ValueError:
        return []

    try:
        target_host, target_ssh_user, target_ssh_port = _get_host_info(entry, "target")
    except ValueError:
        return []

    source_path = entry.get("source_path", "")
    target_path = entry.get("target_path", "")
    if not source_path or not target_path:
        return []

    connection = build_connection_string(source_host, ssh_user)

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
    cmd_str = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout={ssh_connect_timeout} {connection} '{cmd_str}'"

    return [{"label": "Rsync", "cmd": full_cmd}]


def run():
    from astrapi.core.modules.scheduler.job_runner import run_all
    run_all("rsync", _get_config(), run_single)


def run_single(job_id, entry=None):
    if entry is None:
        entry = _get_entry(_get_config(), job_id)
    if entry is None:
        log("ERROR", f"Rsync-Eintrag '{job_id}' nicht gefunden")
        return
    with log_context("rsync", job_id):
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' gestartet ===")

        try:
            source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
        except ValueError as e:
            log("ERROR", str(e))
            return

        try:
            target_host, target_ssh_user, target_ssh_port = _get_host_info(entry, "target")
        except ValueError as e:
            log("ERROR", str(e))
            return

        hosts = [(h, u) for h, u in [(source_host, ssh_user), (target_host, target_ssh_user)] if h and not is_local(h)]
        if not require_hosts(hosts):
            return
        _rsync(entry, source_host, ssh_user, target_host)
        from datetime import datetime
        _patch_item("rsync", job_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"))
        log("INFO", f"=== Rsync '{entry.get('description', job_id)}' abgeschlossen ===")


def _rsync(entry, source_host: str, ssh_user: str, target_host: str):
    source_path = entry.get("source_path", "")
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
    connection = build_connection_string(source_host, ssh_user)

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

    src_label = source_path if connection == "local" else f"{connection}:{source_path}"
    log("INFO", f"Quelle : {src_label}")
    log("INFO", f"Ziel   : {target}")

    cmd = ["rsync", "-av", "--itemize-changes", "--stats", source_path, target]
    if rsync_delete:
        cmd.append("--delete")
    if rsync_compress:
        cmd.append("-z")

    log("INFO", f"Befehl : {' '.join(cmd)}")

    try:
        result = run_cmd(cmd, connection, ssh_connect_timeout=ssh_connect_timeout)
        for line in (result.stdout or "").splitlines():
            if line.strip():
                log("INFO", line)
        log("INFO", "Rsync erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Rsync fehlgeschlagen:")
        for line in (e.stdout or "").splitlines():
            if line.strip():
                log("INFO", line)
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
