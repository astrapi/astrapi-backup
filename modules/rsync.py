import subprocess
import yaml
from helpers.logger import log

from config import config
from helpers.cmd import run_cmd

with open("config/rsync.yaml", "r") as f: 
    CONFIG = yaml.safe_load(f)

def run():
    for job_id, entries in CONFIG.items(): 
        for entry in entries:
            if not entry.get("enabled", False):
                continue

            _rsync(entry)

def _rsync(entry):
    source_host = entry["source_host"]
    source_path = entry["source_path"]
    target_host = entry["target_host"]
    target_path = entry["target_path"]
    connection = build_connection_string(source_host)

    base_cmd = [
        "rsync", 
        "-av", 
        "--delete", 
        "--itemize-changes",
        source_path
    ]

    if target_host == "local":
        cmd = [
            *base_cmd,
            target_path
        ]    
    else:
        cmd = [
            *base_cmd,
            f"{target_host}:{target_path}"
        ] 

    try:
        result = run_cmd(cmd, connection)
        log("INFO", f"Rsync erfolgreich.")
    except subprocess.CalledProcessError as e:
        log("WARNING", "Rsync fehlgeschlagen:")
        if e.stderr:
            log("ERROR", e.stderr.strip())
        else:
            log("ERROR", "Unbekannter Fehler.")

# def run2():
#     for job_id, entries in SYNC_CONFIG.items():
#         log("INFO", f"rsync für '{job_id}'")
#         for entry in entries:

#             if not entry.get("enabled", False):
#                 continue

#             source_host = entry["source_host"]
#             source_path = entry["source_path"]
#             target_host = entry["target_host"]
#             target_path = entry["target_path"]

#             is_source_local = (source_host == "local")
#             is_target_local = (target_host == "local")

#             source = source_path

#             if is_target_local:
#                 target = target_path
#             else:
#                 target = f"{target_host}:{target_path}"

#             base_cmd = [
#                 "rsync", 
#                 "-av", 
#                 "--delete", 
#                 "--itemize-changes", 
#                 source, 
#                 target
#             ]

#             if is_source_local:
#                 cmd = base_cmd
                
#                 try:
#                     if config.debug:
#                         log("DEBUG", f"{' '.join(cmd)}")
#                     else:
#                         subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#                         log("INFO", f"rsync erfolgreich: {source} → {target}")
#                 except subprocess.CalledProcessError:
#                     log("ERROR", f"rsync fehlgeschlagen: {source} → {target}")
#             else:
#                 if is_empty_remote(source_host, target_path): 
#                     log("ERROR", f"Quelle ist leer: {source_host}:{target_path} → rsync abgebrochen") 
#                     continue
#                 else:                
#                     cmd = ["ssh", f"backupadm@{source_host}", " ".join(base_cmd)]

#                     try:
#                         if config.debug:
#                             log("DEBUG", f"{' '.join(cmd)}")
#                         else:
#                             subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#                             log("INFO", f"rsync erfolgreich: {source} → {target}")
#                     except subprocess.CalledProcessError:
#                         log("ERROR", f"rsync fehlgeschlagen: {source} → {target}")

# def is_empty_remote(source_host: str, target_path: str) -> bool:
#     # Debug-Modus: nichts ausführen, immer False zurückgeben
#     if config.debug:
#         log("DEBUG", f"Skip is_empty_remote({source_host}, {target_path}) wegen Debug-Modus")
#         return False

#     cmd = [
#         "ssh",
#         f"backupadm@{source_host}",
#         f'test -z "$(ls -A {target_path})"'
#     ]

#     result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

#     # returncode == 0 → test war TRUE → Verzeichnis ist leer
#     return result.returncode == 0

def build_connection_string(host: str, ssh_user: str | None = None) -> str:
    if host == "local":
        return "local"
    return f"{ssh_user or 'backupadm'}@{host}"