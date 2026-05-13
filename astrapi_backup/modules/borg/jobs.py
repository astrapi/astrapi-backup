# modules/borg/jobs.py
import os
import subprocess
from datetime import datetime

from astrapi_core.system.cmd import build_connection_string, is_local, run_cmd
from astrapi_core.system.logger import log, log_context
from astrapi_core.system.reachability import require_hosts
from astrapi_core.ui.settings_registry import get_module as _get_module_setting

from astrapi_backup.api.storage import load_config as _load_config
from astrapi_backup.api.storage import patch_item as _patch_item
from astrapi_backup.modules.borg.utils import borg_bin_for as _borg_bin_for
from astrapi_backup.modules.borg.utils import borg_env as _borg_env


def _get_config():
    return _load_config("borg")


def _s(key, default):
    return _get_module_setting("borg", key, default)


_STATUS_ORDER = {"ok": 0, "warning": 1, "error": 2}


def _worst(a: str, b: str) -> str:
    return a if _STATUS_ORDER.get(a, 0) >= _STATUS_ORDER.get(b, 0) else b


def _get_host_info(entry: dict, host_type: str = "source") -> tuple[str, str, int]:
    """Löst host/ssh_user/ssh_port über das Remote-Device auf."""
    remote_id_key = f"{host_type}_remote_id"
    remote_id = entry.get(remote_id_key)
    if not remote_id:
        raise ValueError(f"Job missing: '{remote_id_key}' nicht konfiguriert")
    from astrapi_backup.modules.remotes.service import get_remote_ssh

    return get_remote_ssh(remote_id)


def preview(job_id) -> list[dict]:
    """Gibt die Befehle zurück, die bei run_single ausgeführt würden."""
    entry = _get_config().get(str(job_id))
    if entry is None:
        return []

    try:
        source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    try:
        target_host, target_ssh_user, target_ssh_port = _get_host_info(entry, "target")
    except ValueError:
        target_host = None
        target_ssh_user = None

    src_local = is_local(source_host)
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    repo = _repo(
        source_host, target_host, entry.get("target_path"), src_local, ssh_user, target_ssh_user
    )
    archive = f"{repo}::{archive_name}"
    src = f"{entry.get('source_path')}/./"

    def _fmt(parts, connection):
        cmd_str = " ".join(parts) if isinstance(parts, list) else parts
        if connection == "local":
            return cmd_str
        return f"ssh -o BatchMode=yes -o ConnectTimeout=10 {connection} '{cmd_str}'"

    conn = "local" if src_local else build_connection_string(source_host, ssh_user)

    commands = []

    # Pre-Hook
    if entry.get("pre"):
        hooks = entry["pre"]
        if isinstance(hooks, str):
            hooks = [l for l in hooks.split("\n") if l]
        cmd = "; ".join(hooks)
        if cmd:
            commands.append({"label": "Pre-Hook", "cmd": _fmt(cmd, conn)})

    # Borg Backup
    compression = _s("compression", "auto,zstd")
    base_cmd = [
        "BORG_PASSPHRASE=***",
        _borg_bin_for(entry.get("source_remote_id")),
        "create",
        "--verbose",
        "--stats",
        "--compression",
        compression,
        "--exclude-caches",
    ]
    for pattern in entry.get("exclude", []):
        safe = f"'{pattern}'" if any(c in pattern for c in "*?[") else pattern
        base_cmd.extend(["--exclude", safe])
    commands.append({"label": "Borg Backup", "cmd": _fmt([*base_cmd, archive, src], conn)})

    # Post-Hook
    if entry.get("post"):
        hooks = entry["post"]
        if isinstance(hooks, str):
            hooks = [l for l in hooks.split("\n") if l]
        cmd = "; ".join(hooks)
        if cmd:
            commands.append({"label": "Post-Hook", "cmd": _fmt(cmd, conn)})

    # Borg Prune
    keep_daily = _s("keep_daily", "7")
    keep_weekly = _s("keep_weekly", "4")
    keep_monthly = _s("keep_monthly", "12")
    keep_yearly = _s("keep_yearly", "5")
    keep_within = _s("keep_within", "7")
    prune_cmd = [
        "BORG_PASSPHRASE=***",
        _borg_bin_for(entry.get("source_remote_id")),
        "prune",
        f"--keep-daily={keep_daily}",
        f"--keep-weekly={keep_weekly}",
        f"--keep-monthly={keep_monthly}",
        f"--keep-yearly={keep_yearly}",
    ]
    if keep_within and str(keep_within) != "0":
        prune_cmd.append(f"--keep-within={keep_within}d")
    prune_cmd.append(repo)
    commands.append({"label": "Borg Prune", "cmd": _fmt(prune_cmd, conn)})

    # Borg Compact
    if _s("compact_after_prune", "1") in ("1", "true", True):
        compact_cmd = [
            "BORG_PASSPHRASE=***",
            _borg_bin_for(entry.get("source_remote_id")),
            "compact",
            repo,
        ]
        commands.append({"label": "Borg Compact", "cmd": _fmt(compact_cmd, conn)})

    return commands


def run():
    from astrapi_core.system.runner import run_all

    run_all("borg", _get_config(), run_single)


def run_single(job_id, entry=None):
    if entry is None:
        entry = _get_config().get(str(job_id))
    if entry is None:
        log("ERROR", f"Borg-Eintrag '{job_id}' nicht gefunden")
        return

    with log_context("borg", job_id):
        log("INFO", f"=== Borg '{entry.get('description', job_id)}' gestartet ===")

        try:
            source_host, ssh_user, ssh_port = _get_host_info(entry, "source")
        except ValueError as e:
            log("ERROR", str(e))
            return

        try:
            target_host, target_ssh_user, target_ssh_port = _get_host_info(entry, "target")
        except ValueError:
            target_host = None
            target_ssh_user = None

        src_local = is_local(source_host)
        hosts = []
        if not src_local:
            hosts.append((source_host, ssh_user))
        if target_host and not is_local(target_host):
            hosts.append((target_host, target_ssh_user))
        if not require_hosts(hosts):
            _patch_item(
                "borg",
                job_id,
                last_run=datetime.now().strftime("%d.%m.%Y %H:%M"),
                last_status="error",
            )
            return
        status = "ok"
        if entry.get("pre"):
            status = _worst(status, _hook("pre", entry, source_host, ssh_user))
        status = _worst(status, _backup(entry, source_host, ssh_user, target_host, target_ssh_user))
        if entry.get("post"):
            status = _worst(status, _hook("post", entry, source_host, ssh_user))
        status = _worst(status, _prune(entry, source_host, ssh_user, target_host, target_ssh_user))
        if _s("compact_after_prune", "1") in ("1", "true", True):
            status = _worst(
                status, _compact(entry, source_host, ssh_user, target_host, target_ssh_user)
            )
        from astrapi_backup.modules.borg import cache as _cache

        _cache.update(job_id, entry)
        _patch_item(
            "borg", job_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"), last_status=status
        )
        log("INFO", f"=== Borg '{entry.get('description', job_id)}' abgeschlossen ===")


def _hook(phase: str, entry, host: str, ssh_user: str) -> str:
    connection = build_connection_string(host, ssh_user)
    hooks = entry.get(phase) or []
    if isinstance(hooks, str):
        hooks = [l for l in hooks.split("\n") if l]
    cmd = "; ".join(hooks)
    if not cmd:
        return "ok"
    try:
        run_cmd(cmd, connection, env=_borg_env())
        log("INFO", f"Hook '{phase}' erfolgreich")
        return "ok"
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Hook '{phase}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
        return "error"


def _local_fqdn() -> str:
    """
    FQDN dieses Servers – wird als SSH-Ziel für remote→lokal Borg-Repos genutzt.
    Konfigurierbar via LOCAL_FQDN in config/secrets.env (empfohlen).
    Fallback: socket.getfqdn() – kann unter manchen Systemen eine IP zurückgeben.
    """
    configured = os.getenv("LOCAL_FQDN", "").strip()
    if configured:
        return configured
    import ipaddress
    import socket

    fqdn = socket.getfqdn()
    # Fallback auf Hostname wenn getfqdn() eine IP-Adresse (v4 oder v6) zurückgibt
    if fqdn:
        try:
            ipaddress.ip_address(fqdn)
        except ValueError:
            return fqdn  # Kein gültiges IP-Format → ist ein Hostname
    return socket.gethostname()


def _repo(
    source_host: str,
    target_host: str,
    target_path: str,
    src_local: bool = False,
    ssh_user: str = None,
    target_ssh_user: str = None,
) -> str:
    """
    Borg-Repository-Pfad aus Sicht des ausführenden Hosts (source_host).

    source lokal  + target lokal   →  /pfad
    source lokal  + target remote  →  target_ssh_user@target:/pfad
    source remote + target lokal   →  ssh_user@backup01.fqdn:/pfad
    source remote + target remote  →  target_ssh_user@target:/pfad
    """
    if is_local(target_host):
        if src_local or is_local(source_host):
            return target_path
        else:
            return f"{ssh_user}@{_local_fqdn()}:{target_path}"
    else:
        return f"{target_ssh_user}@{target_host}:{target_path}"


def _backup(
    entry, source_host: str, ssh_user: str, target_host: str, target_ssh_user: str = None
) -> str:
    src_local = is_local(source_host)
    connection = build_connection_string(source_host, ssh_user) if not src_local else "local"
    archive_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    env = _borg_env()
    borg = _borg_bin_for(entry.get("source_remote_id"))

    repo = _repo(
        source_host, target_host, entry.get("target_path"), src_local, ssh_user, target_ssh_user
    )
    archive = f"{repo}::{archive_name}"
    src = f"{entry.get('source_path')}/./"

    compression = _s("compression", "auto,zstd")
    base_cmd = [
        borg,
        "create",
        "--verbose",
        "--stats",
        "--compression",
        compression,
        "--exclude-caches",
    ]
    for pattern in entry.get("exclude", []):
        # Wildcards in Quotes einschliessen damit die Remote-Shell sie nicht expandiert
        safe = f"'{pattern}'" if any(c in pattern for c in "*?[") else pattern
        base_cmd.extend(["--exclude", safe])

    if src_local:
        cmd = [*base_cmd, archive, src]
    else:
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, archive, src]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Backup erfolgreich.")
        return "ok"
    except subprocess.CalledProcessError as e:
        # RC=1: Borg-Warnung (nicht lesbare Dateien) – Backup trotzdem gültig
        # RC=2: echter Fehler
        if e.returncode == 1:
            stderr = e.stderr.strip() if e.stderr else ""
            log(
                "WARNING",
                f"Borg-Backup mit Warnungen abgeschlossen:\n{stderr}"
                if stderr
                else "Borg-Backup mit Warnungen abgeschlossen.",
            )
            return "warning"
        else:
            log("WARNING", "Borg-Backup fehlgeschlagen")
            log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
            return "error"


def _prune(
    entry, source_host: str, ssh_user: str, target_host: str, target_ssh_user: str = None
) -> str:
    src_local = is_local(source_host)
    connection = build_connection_string(source_host, ssh_user) if not src_local else "local"

    env = _borg_env()
    borg = _borg_bin_for(entry.get("source_remote_id"))

    repo = _repo(
        source_host, target_host, entry.get("target_path"), src_local, ssh_user, target_ssh_user
    )

    keep_daily = _s("keep_daily", "7")
    keep_weekly = _s("keep_weekly", "4")
    keep_monthly = _s("keep_monthly", "12")
    keep_yearly = _s("keep_yearly", "5")
    keep_within = _s("keep_within", "7")

    base_cmd = [
        borg,
        "prune",
        f"--keep-daily={keep_daily}",
        f"--keep-weekly={keep_weekly}",
        f"--keep-monthly={keep_monthly}",
        f"--keep-yearly={keep_yearly}",
    ]
    if keep_within and str(keep_within) != "0":
        base_cmd.append(f"--keep-within={keep_within}d")

    if src_local:
        cmd = [*base_cmd, repo]
    else:
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd, repo]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Prune erfolgreich.")
        return "ok"
    except subprocess.CalledProcessError as e:
        log("WARNING", "Borg-Prune fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
        return "error"


def _compact(
    entry, source_host: str, ssh_user: str, target_host: str, target_ssh_user: str = None
) -> str:
    src_local = is_local(source_host)
    connection = build_connection_string(source_host, ssh_user) if not src_local else "local"

    env = _borg_env()
    borg = _borg_bin_for(entry.get("source_remote_id"))

    repo = _repo(
        source_host, target_host, entry.get("target_path"), src_local, ssh_user, target_ssh_user
    )
    base_cmd = [borg, "compact", repo]

    if src_local:
        cmd = base_cmd
    else:
        cmd = [f"BORG_PASSPHRASE={env['BORG_PASSPHRASE']}", *base_cmd]

    try:
        run_cmd(cmd, connection, env=env)
        log("INFO", "Borg-Compact erfolgreich.")
        return "ok"
    except subprocess.CalledProcessError as e:
        log("WARNING", "Borg-Compact fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
        return "error"
