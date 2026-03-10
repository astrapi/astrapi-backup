# modules/borg.py
import os
import subprocess
from datetime import datetime

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.secrets import get_secret
from helpers.cmd import run_cmd, build_connection_string, is_local
from helpers.debug import is_debug

from api.storage import load_config as _load_config
def _get_config(): return _load_config("borg")


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
        log("ERROR", f"Borg-Eintrag '{job_id}' nicht gefunden")
        return

    log_item_id = f"{job_id}_debug" if is_debug() else job_id
    set_log_context("borg", log_item_id)
    try:
        log("INFO", f"=== Borg '{entry.get('description', job_id)}' gestartet ===")
        if not is_debug():
            hosts = [h for h in {entry.get("source_host"), entry.get("target_host")}
                     if h and not is_local(h)]
            if not require_hosts(hosts):
                return
        if entry.get("pre"):
            _hook("pre", entry)
        _backup(entry)
        if entry.get("post"):
            _hook("post", entry)
        _prune(entry)
        log("INFO", f"=== Borg '{entry.get('description', job_id)}' abgeschlossen ===")
    finally:
        clear_log_context()


def _hook(phase: str, entry):
    host       = entry.get("source_host")
    ssh_user   = entry.get("ssh_user") or "backupadm"
    connection = build_connection_string(host, ssh_user)
    hooks = entry.get(phase) or []
    if isinstance(hooks, str):
        hooks = [l for l in hooks.split("\n") if l]
    cmd = "; ".join(hooks)
    if not cmd:
        return
    try:
        run_cmd(cmd, connection)
        log("INFO", f"Hook '{phase}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Hook '{phase}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def _local_fqdn() -> str:
    """
    FQDN dieses Servers – wird als SSH-Ziel für remote→lokal Borg-Repos genutzt.
    Konfigurierbar via LOCAL_FQDN in config/secrets.env (empfohlen).
    Fallback: socket.getfqdn() – kann unter manchen Systemen eine IP zurückgeben.
    """
    configured = os.getenv("LOCAL_FQDN", "").strip()
    if configured:
        return configured
    import socket
    fqdn = socket.getfqdn()
    # Fallback auf Hostname wenn getfqdn() eine IP zurückgibt
    if fqdn and not fqdn.replace(".", "").isdigit():
        return fqdn
    return socket.gethostname()


def _repo(source_host: str, target_host: str, target_path: str) -> str:
    """
    Borg-Repository-Pfad aus Sicht des ausführenden Hosts (source_host).

    source lokal  + target lokal   →  /pfad
    source lokal  + target remote  →  backupadm@target:/pfad
    source remote + target lokal   →  backupadm@backup01.fqdn:/pfad
    source remote + target remote  →  backupadm@target:/pfad
    """
    if is_local(target_host):
        if is_local(source_host):
            return target_path
        else:
            return f"backupadm@{_local_fqdn()}:{target_path}"
    else:
        return f"backupadm@{target_host}:{target_path}"


def _backup(entry):
    source_host  = entry.get("source_host")
    target_host  = entry.get("target_host")
    # Borg läuft immer als backupadm – ssh_user gilt nur für Hooks
    connection   = build_connection_string(source_host, "backupadm")
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    repo    = _repo(source_host, target_host, entry.get("target_path"))
    archive = f"{repo}::{archive_name}"
    src     = f"{entry.get('source_path')}/./"

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg", "create",
        "--verbose", "--stats", "--compression", "auto,zstd",
        "--exclude-caches",
    ]
    for pattern in entry.get("exclude", []):
        # Wildcards in Quotes einschliessen damit die Remote-Shell sie nicht expandiert
        safe = f"\'{pattern}\'" if any(c in pattern for c in "*?[") else pattern
        base_cmd.extend(["--exclude", safe])

    if is_local(source_host):
        cmd = [*base_cmd, archive, src]
    else:
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, archive, src]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Backup erfolgreich.")
    except subprocess.CalledProcessError as e:
        # RC=1: Borg-Warnung (nicht lesbare Dateien) – Backup trotzdem gültig
        # RC=2: echter Fehler
        if e.returncode == 1:
            stderr = e.stderr.strip() if e.stderr else ""
            log("WARNING", f"Borg-Backup mit Warnungen abgeschlossen:\n{stderr}" if stderr else "Borg-Backup mit Warnungen abgeschlossen.")
        else:
            log("WARNING", "Borg-Backup fehlgeschlagen")
            log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def _prune(entry):
    source_host = entry.get("source_host")
    target_host = entry.get("target_host")
    # Borg läuft immer als backupadm – ssh_user gilt nur für Hooks
    connection  = build_connection_string(source_host, "backupadm")

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    repo = _repo(source_host, target_host, entry.get("target_path"))

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg", "prune",
        "--keep-daily=7", "--keep-weekly=4", "--keep-monthly=12", "--keep-yearly=5",
    ]

    if is_local(source_host):
        cmd = [*base_cmd, repo]
    else:
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, repo]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Prune erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Borg-Prune fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
