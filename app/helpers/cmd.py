# helpers/cmd.py
import os
import socket
import subprocess
from functools import lru_cache
from helpers.logger import log
from config import is_debug

# Timeouts für Subprocess-Aufrufe.
# Backup-Jobs können stundenlang laufen → kein globaler Timeout.
# Aber: Info-Abfragen (borg info, borg list) und SSH-Verbindungstests
# sollen nicht ewig hängen.
TIMEOUT_INFO    = 60    # borg info, borg list, rsync --dry-run
TIMEOUT_CONNECT = 15    # SSH-Verbindungstest
TIMEOUT_BACKUP  = None  # Backup selbst: kein Timeout (kann Stunden dauern)


@lru_cache(maxsize=1)
def _local_hostnames() -> frozenset:
    names = set()
    names.add(socket.gethostname())
    names.add(socket.getfqdn())
    try:
        names.add(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    return frozenset(names)


def is_local(host: str) -> bool:
    if host == "local":
        return True
    return host in _local_hostnames()


def build_connection_string(host: str, ssh_user: str = "backupadm") -> str:
    if is_local(host):
        return "local"
    return f"{ssh_user}@{host}"


def run_cmd(cmd, connection: str, env=None, timeout=TIMEOUT_BACKUP):
    if isinstance(cmd, list):
        cmd = " ".join(cmd)
    if connection == "local":
        return run_cmd_local(cmd, env, timeout=timeout)
    else:
        return run_cmd_remote(cmd, connection, env, timeout=timeout)


def run_cmd_local(cmd, env=None, timeout=TIMEOUT_BACKUP):
    final_cmd = ["bash", "-c", cmd]
    if is_debug():
        log("DEBUG", "LOCAL: bash -c " + repr(cmd))
        return True
    try:
        result = subprocess.run(
            final_cmd, check=True, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        log("ERROR", f"Timeout ({timeout}s) beim lokalen Befehl: {cmd[:120]}")
        raise


def run_cmd_remote(cmd, connection, env=None, timeout=TIMEOUT_BACKUP):
    final_cmd = ["ssh", "-o", "BatchMode=yes",
                 "-o", "ConnectTimeout=10",
                 connection, cmd]
    if is_debug():
        log("DEBUG", "REMOTE: ssh " + connection + " " + repr(cmd))
        return True
    try:
        result = subprocess.run(
            final_cmd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        log("ERROR", f"Timeout ({timeout}s) beim Remote-Befehl auf {connection}: {cmd[:120]}")
        raise
