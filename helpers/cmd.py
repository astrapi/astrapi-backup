# helpers/cmd.py
import os
import socket
import subprocess
from functools import lru_cache
from helpers.logger import log
from config import is_debug


@lru_cache(maxsize=1)
def _local_hostnames() -> frozenset:
    """Alle Namen unter denen dieser Host bekannt ist."""
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


def run_cmd(cmd, connection: str, env=None):
    if isinstance(cmd, list):
        cmd = " ".join(cmd)

    if connection == "local":
        return run_cmd_local(cmd, env)
    else:
        return run_cmd_remote(cmd, connection, env)


def run_cmd_local(cmd, env=None):
    final_cmd = ["bash", "-c", cmd]
    if is_debug():
        log("DEBUG", "LOCAL: bash -c " + repr(cmd))
        return True
    result = subprocess.run(
        final_cmd, check=True, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result


def run_cmd_remote(cmd, connection, env=None):
    # cmd wird als einzelnes Argument an SSH übergeben → Remote-Login-Shell
    # interpretiert Semikolons, source, Backticks etc. korrekt.
    # KEIN bash -c wrapper – das würde eine zweite Shell-Ebene einführen
    # und Quoting (Backticks, Anführungszeichen) doppelt auswerten.
    final_cmd = ["ssh", "-o", "BatchMode=yes", connection, cmd]
    if is_debug():
        log("DEBUG", "REMOTE: ssh -o BatchMode=yes " + connection + " " + repr(cmd))
        return True
    result = subprocess.run(
        final_cmd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    return result
