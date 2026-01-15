import os
import subprocess
import yaml
from datetime import datetime
from dotenv import load_dotenv

from helpers.logger import log
from helpers.secrets import get_secret


from helpers.cmd import run_cmd
from config import config

with open("config/borg.yaml", "r") as f: 
    BORG_CONFIG = yaml.safe_load(f)

def run(): 
    for job_id, entry in BORG_CONFIG.items(): 
        if not entry.get("enabled", False):
            continue

        if entry.get("pre"):
            _hook("pre", entry)

        _backup(entry)

        if entry.get("post"):
            _hook("post", entry)

        _prune(entry)

def _hook(phase: str, entry):
    host = entry.get("source_host") 
    ssh_user = entry.get("ssh_user") 
    
    connection = build_connection_string(host, ssh_user)

    hook = entry.get(phase)
    
    cmd = "; ".join(hook)
    try:
        result = run_cmd(cmd, connection)
        log("INFO", f"Hook '{phase}' für '{host}' erfolgreich")
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Hook '{phase}' für '{host}' fehlgeschlagen")
        if e.stderr:
            log("ERROR", e.stderr.strip())
        else:
            log("ERROR", "Unbekannter Fehler.")

def _backup(entry):
    host = entry.get("source_host")
    connection = build_connection_string(host)
    
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg",
        "create",
        "--verbose",
        "--stats",
        "--compression", "auto,zstd",
        "--exclude-caches",
        "--exclude", "'*/lost+found'"
    ]

    if connection == "local":
        cmd = [
            *base_cmd,
            f"{entry.get('target_path')}::{archive_name}",
            f"{entry.get('source_path')}/./"
        ]
    else:
        cmd = [
            f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}",
            *base_cmd,
            f"backupadm@{entry.get('target_host')}:{entry.get('target_path')}::{archive_name}",
            f"{entry.get('source_path')}/./"
        ]

    try:
        result = run_cmd(cmd, connection, env=env)
        log("INFO", f"Borg-Backup erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Borg-Backup fehlgeschlagen:")
        if e.stderr:
            log("ERROR", e.stderr.strip())
        else:
            log("ERROR", "Unbekannter Fehler.")

def _prune(entry):
    host = entry.get("source_host")
    connection = build_connection_string(host)

    keep_daily = 7
    keep_weekly = 4
    keep_monthly = 12
    keep_yearly = 5

    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_secret("BORG_PASSPHRASE")

    base_cmd = [
        "/var/lib/backupadm/.venv/bin/borg",
        "prune",
        f"--keep-daily={keep_daily}",
        f"--keep-weekly={keep_weekly}",
        f"--keep-monthly={keep_monthly}",
        f"--keep-yearly={keep_yearly}"
    ]

    if connection == "local":
        cmd = [
            *base_cmd,
            f"{entry.get('target_path')}"
        ]
    else:
        cmd = [
            f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}",
            *base_cmd,
            f"backupadm@{entry.get('target_host')}:{entry.get('target_path')}",
        ]

    try:
        result = run_cmd(cmd, connection, env=env)
        log("INFO", f"Borg-Prune erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Borg-Prune fehlgeschlagen:")
        if e.stderr:
            log("ERROR", e.stderr.strip())
        else:
            log("ERROR", "Unbekannter Fehler.")

def build_connection_string(host: str, ssh_user: str | None = None) -> str:
    if host == "local":
        return "local"
    return f"{ssh_user or 'backupadm'}@{host}"

