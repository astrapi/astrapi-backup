#!/usr/bin/env python3
import subprocess, json, datetime, os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

def get_vm_list():
    cmd = [
        "ssh", "backupadm@proxmox01.simpsons.lan",
        "sudo", "pvesh", "get", "/cluster/resources",
        "--type", "vm", "--output-format", "json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    vm_list = []
    for vm in data:
        if vm.get("tags") and "backup" in vm["tags"]:
            vm_list.append((vm["vmid"], vm["name"], vm["node"]))
    return vm_list

def run_backup(vmid, name, node):
    fqdn = f"{node}.simpsons.lan"
    cmd = [
        "ssh", f"backupadm@{fqdn}",
        "sudo", "/usr/bin/vzdump",
        str(vmid),
        "--fleecing", "0",
        "--node", node,
        "--mode", "snapshot",
        "--notification-mode", "notification-system",
        "--notes-template", "{{guestname}}",
        "--storage", "backup01",
        "--all", "0"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        status = "OK"
    else:
        status = f"FEHLER: {result.stderr.strip()}"
    return (vmid, name, node, status)

def process_node(node, vms, results):
    fqdn = f"{node}.simpsons.lan"
    for vmid, name, _ in vms:
        results.append(run_backup(vmid, name, node))

def run_host_backup():
    for node in ["proxmox01", "proxmox02", "proxmox03"]:
        cmd = [
            "ssh", f"backupadm@{node}",
            "sudo", "/usr/local/bin/backup-host"
        ]
        print(f"→ Starte Backup auf {node}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✔ Backup auf {node} erfolgreich")
            #print(result.stdout)
        else:
            print(f"✘ Fehler beim Backup auf {node}")
            #print(result.stderr)

def run_verify():
    cmd = [
        "sudo", "/usr/sbin/proxmox-backup-manager",
        "verify", "storage",
        "--read-threads", "1",
        "--verify-threads", "4",
        "--ignore-verified", "true"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return "OK" if result.returncode == 0 else f"FEHLER: {result.stderr.strip()}"

def run_sync():
    results = []
    for remote in ["backup02", "backup03"]:
        cmd = [
            "ssh", f"backupadm@{remote}",
            "sudo", "proxmox-backup-manager", "sync-job", "run", "sync-storage-simpsons"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results.append((remote, "OK"))
        else:
            results.append((remote, f"FEHLER: {result.stderr.strip()}"))
    return results

def run_sync_extern():
    results = []
    for remote in ["backup02"]:
        cmd = [
            "ssh", f"backupadm@{remote}",
            "sudo", "proxmox-backup-manager", "sync-job", "run", "sync-storage-extern"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            results.append((remote, "OK"))
        else:
            results.append((remote, f"FEHLER: {result.stderr.strip()}"))
    return results

def backup_pbs():
    vms = get_vm_list()
    print("Gefundene CT/VM mit Tag 'backup':")
    for vmid, name, node in vms:
        print(f"{vmid}\t{name}\t{node}")

    # Gruppieren nach Node
    grouped = defaultdict(list)
    for vmid, name, node in vms:
        grouped[node].append((vmid, name, node))

    results = []
    print("\nStarte Backups pro Node...")
    # Parallel pro Node
    with ThreadPoolExecutor(max_workers=len(grouped)) as executor:
        futures = [executor.submit(process_node, node, grouped[node], results) for node in grouped]
        for f in futures:
            f.result()  # warten bis alle Nodes fertig sind

    # Zusammenfassung sortiert nach VMID
    print("\n=== Zusammenfassung Backups ===")
    for vmid, name, node, status in sorted(results, key=lambda x: x[0]):
        print(f"{vmid}\t{name}\t{node}.simpsons.lan\t{status}")

    run_host_backup()

    # Verify & Sync lokal
    print("\n=== Verify-Job ===")
    print(run_verify())

    print("\n=== Sync-Job ===")
    print(run_sync())
    print(run_sync_extern())

# if __name__ == "__main__":
#     main()
