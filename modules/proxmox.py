import os
import subprocess
import json
import yaml
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from helpers.logger import log
from helpers.secrets import get_secret
from config import config

from helpers.cmd import run_cmd

with open("config/proxmox.yaml", "r") as f: 
    CONFIG = yaml.safe_load(f)

def run():
    run_lxc_backup()
    run_host_backup()
    run_jobs()

def run_lxc_backup():
    grouped = group_by_node(CONFIG["lxc"])

    with ThreadPoolExecutor(max_workers=len(grouped)) as executor:
        futures = []

        for node, jobs in grouped.items():
            futures.append(
                executor.submit(_run_lxc_backup, node, jobs)
            )

        for f in futures:
            f.result()

def _run_lxc_backup(node, jobs):
    for job in jobs:
        vmid = job["vmid"]
        name = job["name"]
        fqdn = f"{node}.simpsons.lan"

        cmd = [
            "sudo", 
            "/usr/bin/vzdump",
            str(vmid),
            "--fleecing", "0",
            "--node", node,
            "--mode", "snapshot",
            "--notification-mode", "notification-system",
            "--notes-template", "{{guestname}}",
            "--storage", "backup01",
            "--all", "0"
        ]

        try:
            result = run_cmd(cmd, node)
            log("INFO", f"Proxmox-Backup '{name}' erfolgreich")
        except subprocess.CalledProcessError as e:
            log("WARNING", f"Proxmox-Backup '{name}' fehlgeschlagen")
            if e.stderr:
                log("ERROR", e.stderr.strip())
            else:
                log("ERROR", "Unbekannter Fehler.")

def run_host_backup():
    for host, entry in CONFIG["host"].items():
        if not entry.get("enabled", True):
            continue

        connection = build_connection_string(host)

        pxar_sources = [
            "etc.pxar:/etc",
            "home.pxar:/home",
            "opt.pxar:/opt",
            "root.pxar:/root",
            "local.pxar:/usr/local",
        ]

        extra_sources = entry.get("source", [])
        pxar_sources += extra_sources

        env = dict(os.environ)
        env["PBS_REPOSITORY"] = "backup@pbs!backup-host@172.19.18.5:storage" 
        env["PBS_PASSWORD"] = get_secret("PBS_PASSWORD") 
        env["PBS_FINGERPRINT"] = get_secret("PBS_FINGERPRINT")

        base_cmd = [ 
            "sudo", 
            "--preserve-env=PBS_REPOSITORY,PBS_PASSWORD,PBS_FINGERPRINT", 
            "/usr/bin/proxmox-backup-client", 
            "backup", 
            *pxar_sources, 
            "--backup-type", "host", 
            "--backup-id", "$(hostname)", 
            "--ns", "host", 
            "--backup-time", "$(date +%s)" 
        ]

        if connection == "local":
            cmd = base_cmd
        else:
            cmd = [
                f"PBS_REPOSITORY={env['PBS_REPOSITORY']}",
                f"PBS_PASSWORD={env['PBS_PASSWORD']}",
                f"PBS_FINGERPRINT={env['PBS_FINGERPRINT']}",
                *base_cmd
            ]

        try:
            result = run_cmd(cmd, connection, env=env)
            log("INFO", f"Proxmox-Host-Backup '{host}' erfolgreich")
        except subprocess.CalledProcessError as e:
            log("WARNING", f"Proxmox-Host-Backup '{host}' fehlgeschlagen")
            if e.stderr:
                log("ERROR", e.stderr.strip())
            else:
                log("ERROR", "Unbekannter Fehler.")

def run_jobs():
    JOB_ORDER = ["verify", "prune", "sync"]

    for job_type in JOB_ORDER:
        jobs = CONFIG["jobs"].get(job_type, [])

        for job in jobs:
            if not job.get("enabled", True):
                continue

            name = job["name"]
            host = job["host"]

            cmd = [
                "sudo",
                "/usr/sbin/proxmox-backup-manager",
                f"{job_type}-job",
                "run",
                name
            ]

            try:
                result = run_cmd(cmd, host)
                log("INFO", f"{job_type}-job '{name}' auf '{host}' erfolgreich")
            except subprocess.CalledProcessError as e:
                log("WARNING", f"{job_type}-job '{name}' auf '{host}' fehlgeschlagen")
                if e.stderr:
                    log("ERROR", e.stderr.strip())
                else:
                    log("ERROR", "Unbekannter Fehler.")

def group_by_node(lxc_config):
    grouped = defaultdict(list)

    for vmid, entry in lxc_config.items():
        if not entry.get("enabled", True):
            continue

        grouped[entry["node"]].append({
            "vmid": vmid,
            "name": entry["name"],
        })

    return grouped



def build_connection_string(host: str, ssh_user: str | None = None) -> str:
    if host == "local":
        return "local"
    return f"{ssh_user or 'backupadm'}@{host}"