# core/system/reachability.py
import subprocess
from core.system.logger import log
from core.system.cmd import is_local


def check_ssh(host: str, user: str = "backupadm", timeout: int = 5) -> bool:
    result = subprocess.run(
        ["ssh",
         "-o", "BatchMode=yes",
         "-o", f"ConnectTimeout={timeout}",
         "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}",
         "echo ok"],
        capture_output=True, text=True
    )
    return result.returncode == 0 and "ok" in result.stdout


def require_hosts(hosts: list[str], user: str = "backupadm") -> bool:
    all_ok = True
    for host in hosts:
        if is_local(host):          # lokaler Host braucht keinen SSH-Test
            continue
        if not check_ssh(host, user):
            log("WARNING", f"Host nicht erreichbar: {host}")
            log("ERROR", f"SSH-Verbindung zu '{host}' fehlgeschlagen – Ausführung abgebrochen")
            all_ok = False
    return all_ok
