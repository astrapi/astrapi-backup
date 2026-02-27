# modules/borg.py
import os
import subprocess
from datetime import datetime

from helpers.logger import log, set_log_context, clear_log_context
from helpers.reachability import require_hosts
from helpers.secrets import get_secret
from helpers.cmd import run_cmd, build_connection_string, is_local
from config import is_debug

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
    set_log_context("borg", job_id)
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
    host = entry.get("source_host")
    ssh_user = entry.get("ssh_user")
    connection = build_connection_string(host, ssh_user or "backupadm")
    cmd = "; ".join(entry.get(phase))
    try:
        run_cmd(cmd, connection)
        log("INFO", f"Hook '{phase}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Hook '{phase}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def _backup(entry):
    source_host = entry.get("source_host")
    target_host = entry.get("target_host")
    connection = build_connection_string(source_host)
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg", "create",
        "--verbose", "--stats", "--compression", "auto,zstd",
        "--exclude-caches", "--exclude", "'*/lost+found'"
    ]
    for pattern in entry.get("exclude", []):
        base_cmd.extend(["--exclude", f"'{pattern}'"])

    if is_local(source_host):
        # Backup läuft lokal, Ziel ist lokal oder remote
        if is_local(target_host):
            repo = f"{entry.get('target_path')}::{archive_name}"
        else:
            repo = f"backupadm@{target_host}:{entry.get('target_path')}::{archive_name}"
        cmd = [*base_cmd, repo, f"{entry.get('source_path')}/./"]
    else:
        # Backup läuft auf Remote-Host, Borg-Passphrase muss mitgegeben werden
        if is_local(target_host):
            repo = f"{entry.get('target_path')}::{archive_name}"
        else:
            repo = f"backupadm@{target_host}:{entry.get('target_path')}::{archive_name}"
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, repo,
               f"{entry.get('source_path')}/./"]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Backup erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Borg-Backup fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")


def _prune(entry):
    source_host = entry.get("source_host")
    target_host = entry.get("target_host")
    connection = build_connection_string(source_host)

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg", "prune",
        "--keep-daily=7", "--keep-weekly=4", "--keep-monthly=12", "--keep-yearly=5"
    ]

    if is_local(source_host):
        if is_local(target_host):
            repo = entry.get("target_path")
        else:
            repo = f"backupadm@{target_host}:{entry.get('target_path')}"
        cmd = [*base_cmd, repo]
    else:
        if is_local(target_host):
            repo = entry.get("target_path")
        else:
            repo = f"backupadm@{target_host}:{entry.get('target_path')}"
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, repo]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Prune erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Borg-Prune fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
