#!/usr/bin/env python3
import subprocess
import time
import concurrent.futures
from datetime import datetime

import run_backup_pbs
import run_backup_opnsense

BACKUP02_HOST = "backup02.simpsons.lan"
BACKUP02_USER = "backupadm"

def power_on_backup02():
    subprocess.run(["wakeonlan", "68:05:ca:3e:99:7b"], check=True)
    print("→ backup02 gestartet (Wake-on-LAN gesendet)")

def wait_for_backup02():
    print("→ Warte bis backup02 erreichbar ist …")
    while True:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             f"{BACKUP02_USER}@{BACKUP02_HOST}", "echo ok"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and "ok" in result.stdout:
            print("✔ backup02 ist online")
            break
        time.sleep(10)

def run_script(script):
    print(f"→ Starte {script}")
    result = subprocess.run(["python3", script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✔ {script} erfolgreich beendet")
    else:
        print(f"✘ Fehler in {script}")
        print(result.stderr)

def power_off_backup02():
    subprocess.run(
        ["ssh", f"{BACKUP02_USER}@{BACKUP02_HOST}", "sudo shutdown -h now"],
        check=True
    )
    print("→ backup02 heruntergefahren")

def run_pbs():
    """Wrapper für das PBS-Modul."""
    print("→ Starte PBS-Backup-Jobs")
    results = run_backup_pbs.backup_pbs()
    print("✔ PBS-Backup abgeschlossen")
    return results

def main():
    # Startzeit
    start_time = datetime.now()
    print(f"\n=== Backup gestartet um {start_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    # power_on_backup02()
    # wait_for_backup02()

    # run_pbs()
    run_backup_opnsense.backup_opnsense()

    # power_off_backup02()

    # Endezeit
    end_time = datetime.now()
    print(f"\n=== Backup beendet um {end_time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    duration = end_time - start_time
    print(f"Gesamtdauer: {duration}\n")

if __name__ == "__main__":
    main()
