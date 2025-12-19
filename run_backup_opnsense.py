#!/usr/bin/env python3
import subprocess
import datetime
import os
from pathlib import Path
import shutil

# Zielverzeichnis für die OPNsense-Configs
BACKUP_DIR = "/var/lib/backupadm/opnsense"

# Firewalls mit IP und Ziel-Dateiname
FIREWALLS = {
    "firewall01": ("172.19.0.201", "firewall01.xml"),
    "firewall02": ("172.19.0.202", "firewall02.xml"),
}

def make_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def remove_backup_dir():
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)

def copy_config():
    """Holt die Config per scp von einer Firewall."""
    for name, (ip, filename) in FIREWALLS.items():
        cmd = ["scp", 
            "-o", "BatchMode=yes", 
            "-o", "ConnectTimeout=10", 
            f"backupadm@{ip}:/conf/config.xml",
            os.path.join(BACKUP_DIR, filename)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✔ {name}: Config erfolgreich übertragen")
            #return True
        else:
            print(f"✘ {name}: Fehler beim Übertragen der Config")
            print(result.stderr)
            #return False


def get_passphrase():
    return Path("/var/lib/backupadm/.borg_passphrase").read_text().strip()


def run_borg_backup(repo: str, source_dir: str):
    """
    Führt ein Borg-Backup des angegebenen source_dir ins angegebene repo aus.
    Gibt nur Erfolg oder Fehler zurück.
    """
    # Archivname mit aktuellem Datum/Zeit
    archive_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = f"{repo}::{archive_name}"

    # Environment für Borg
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_passphrase()

    # Borg-Befehl
    borg_cmd = [
        "borg",
        "create",
        "--verbose",
        "--stats",
        "--compression", "auto,zstd",
        "--exclude-caches",
        "--exclude", "*lost+found*",
        archive,
        source_dir
    ]

    # Ausführen und nur Erfolg/Fehler melden
    try:
        subprocess.run(borg_cmd, check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✔ Borg-Backup erfolgreich erstellt.")
    except subprocess.CalledProcessError:
        print("✘ Fehler: Borg-Backup fehlgeschlagen.")

def run_borg_prune(repo_path: str,
               keep_hourly: int = 24,
               keep_daily: int = 7,
               keep_weekly: int = 4,
               keep_monthly: int = 12,
               keep_yearly: int = 2):
    
    # Environment für Borg
    env = dict(os.environ)
    env["BORG_PASSPHRASE"] = get_passphrase()
    
    """
    Führt borg prune auf einem Repository aus und gibt nur Erfolg oder Fehler zurück.
    """
    cmd = [
        "borg",
        "prune",
        repo_path,
        f"--keep-hourly={keep_hourly}",
        f"--keep-daily={keep_daily}",
        f"--keep-weekly={keep_weekly}",
        f"--keep-monthly={keep_monthly}",
        f"--keep-yearly={keep_yearly}"
    ]

    try:
        subprocess.run(cmd, check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("✔ Borg prune erfolgreich ausgeführt")
    except subprocess.CalledProcessError:
        print("✘ Fehler: Borg prune ist fehlgeschlagen")

def run_rsync_jobs():
    jobs = [
        # → Backup02
        ("/storage/borg/firewall/", "backup02:/storage/borg/firewall/"),
        ("/storage/borg/firewall/", "backup02:/storage_extern/borg/firewall/"),

        # → Backup03
        ("/storage/borg/firewall/", "backup03:/storage/borg/firewall/"),
    ]

    for src, dst in jobs:
        run_rsync_job(src, dst)

def run_rsync_job(src: str, dst: str) -> bool:
    """
    Führt einen einzelnen Rsync-Job von src nach dst aus.
    Gibt True zurück, wenn erfolgreich, False bei Fehler.
    """
    #print(f"→ Starte Rsync: {src} → {dst}")
    cmd = ["rsync", "-av", "--delete", "--itemize-changes", src, dst]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✔ Rsync erfolgreich {src} → {dst}")
        return True
    else:
        print(f"✘ Fehler {src} → {dst}")
        #print(result.stderr)
        return False

def backup_opnsense():
    start = datetime.datetime.now()
    print(f"\n=== OPNsense-Backup gestartet um {start.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    make_backup_dir()
    copy_config()

    run_borg_backup("/storage/borg/firewall", "/var/lib/backupadm/opnsense/./")

    run_borg_prune("/storage/borg/firewall")

    remove_backup_dir()

    run_rsync_jobs()
    #run_rsync_job("/storage/borg/firewall/", "backup03:/storage/borg/firewall/")

    end = datetime.datetime.now()
    print(f"\n=== OPNsense-Backup beendet um {end.strftime('%Y-%m-%d %H:%M:%S')} ===")

if __name__ == "__main__":
    main()
