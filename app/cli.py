#!/usr/bin/env python3
import subprocess
import time
import yaml
import concurrent.futures
from pathlib import Path
from datetime import datetime

from modules import proxmox
from modules import borg
from modules import rsync

from helpers.logger import log, get_ntfy_logs
from helpers.notify import notify_ntfy

import argparse
from config import config 

BACKUP02_HOST = "backup02.simpsons.lan"
BACKUP02_USER = "backupadm"

_CLI_CONFIG_DIR = Path(__file__).resolve().parent / "config"
with open(_CLI_CONFIG_DIR / "borg.yaml", "r") as f: 
    BORG_CONFIG = yaml.safe_load(f)

def parse_args(): 
    parser = argparse.ArgumentParser(description="Backup / Sync Tool") 
    #parser.add_argument("--dry", action="store_true") 
    #parser.add_argument("--verbose", "-v", action="store_true") 
    parser.add_argument("--debug", action="store_true") 
    parser.add_argument("--borg", action="store_true", help="Führe borg Backups aus")
    parser.add_argument("--rsync", action="store_true", help="Führe rsync Synchronisationen aus")
    parser.add_argument("--proxmox", action="store_true", help="Führe Proxmox Backups aus")
    return parser.parse_args()

def power_on_backup02():
    subprocess.run(["wakeonlan", "68:05:ca:3e:99:7b"], check=True)
    log("→ backup02 gestartet (Wake-on-LAN gesendet)")

def wait_for_backup02():
    log("→ Warte bis backup02 erreichbar ist …")
    while True:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{BACKUP02_USER}@{BACKUP02_HOST}", "echo ok"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and "ok" in result.stdout:
            log("✔ backup02 ist online")
            break
        time.sleep(10)

def run_script(script):
    log(f"→ Starte {script}")
    result = subprocess.run(["python3", script], capture_output=True, text=True)
    if result.returncode == 0:
        log(f"✔ {script} erfolgreich beendet")
    else:
        log(f"✘ Fehler in {script}")
        print(result.stderr)

def power_off_backup02():
    subprocess.run(
        ["ssh", f"{BACKUP02_USER}@{BACKUP02_HOST}", "sudo shutdown -h now"],
        check=True
    )
    log("→ backup02 heruntergefahren")

def format_duration(duration):
    total_seconds = int(duration.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []

    # Stunden
    if hours > 0:
        if hours == 1:
            parts.append("1 Stunde")
        else:
            parts.append(f"{hours} Stunden")

    # Minuten
    if minutes > 0:
        if minutes == 1:
            parts.append("1 Minute")
        else:
            parts.append(f"{minutes} Minuten")

    # Sekunden
    if seconds > 0:
        if seconds == 1:
            parts.append("1 Sekunde")
        else:
            parts.append(f"{seconds} Sekunden")

    # Falls alles 0 ist
    if not parts:
        return "0 Sekunden"

    return " und ".join(parts)



def main():

    args = parse_args() 
    config.debug = args.debug
    config.borg = args.borg
    config.rsync = args.rsync
    config.proxmox = args.proxmox

    start_time = datetime.now()
    log("START", f"{start_time.strftime('%d.%m.%Y %H:%M:%S')}")
    if not config.debug:
        notify_ntfy(get_ntfy_logs("START"), priority="low")

    if not config.debug:
        power_on_backup02()
        wait_for_backup02()

    no_args = not args.borg and not args.rsync and not args.proxmox

    if args.borg or no_args: 
        borg.run() 
        
    if args.rsync or no_args: 
        rsync.run()

    if args.proxmox or no_args: 
        proxmox.run()

    if not config.debug:
        power_off_backup02()

    end_time = datetime.now()
    log("END", f"{end_time.strftime('%d.%m.%Y %H:%M:%S')} \nDauer: {format_duration(end_time - start_time)}")

    if not config.debug:
        notify_ntfy(get_ntfy_logs("WARNING"), priority="high")

    time.sleep(1)

    if not config.debug:
        notify_ntfy(get_ntfy_logs("END"), priority="low")

if __name__ == "__main__":
    main()
