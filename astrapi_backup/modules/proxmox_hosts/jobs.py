# modules/proxmox_hosts.py
#
# Warum kein API-Zugriff?
# proxmox-backup-client muss auf dem zu sichernden Host selbst ausgeführt werden
# und stellt von dort die Verbindung zum PBS-Server her. Weder die Proxmox VE API
# noch die PBS API bieten einen Endpoint, der diesen Client-seitigen Prozess remote
# auslösen kann. POST /nodes/{node}/vzdump (PVE) sichert nur VMs/CTs, nicht
# Host-Dateisysteme. SSH ist daher hier zwingend erforderlich.
#
import os
import subprocess

from astrapi.core.system.logger import log, log_context
from astrapi.core.system.reachability import require_hosts
from astrapi.core.system.cmd import run_cmd, build_connection_string, is_local
from astrapi.core.ui.settings_registry import get_module as _get_module_setting, get as _get_global_setting

from astrapi_backup.api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item
def _get_config(): return _load_config("proxmox_hosts")

_FALLBACK_SOURCES = [
    "etc.pxar:/etc", "home.pxar:/home", "opt.pxar:/opt",
    "root.pxar:/root", "local.pxar:/usr/local",
]

def _default_sources() -> list[str]:
    sources = _get_module_setting("proxmox_hosts", "default_sources", [])
    if isinstance(sources, list):
        return list(sources) if sources else list(_FALLBACK_SOURCES)
    # Fallback für ältere String-Werte (textarea)
    parsed = [s.strip() for s in sources.splitlines() if s.strip()]
    return parsed if parsed else list(_FALLBACK_SOURCES)


def _get_pbs_config(entry: dict) -> dict:
    """Liest PBS-Verbindungsdaten aus dem in den Einstellungen gewählten PBS-Remote."""
    from astrapi_backup.modules.remotes.engine import get_remote
    pbs_remote_id = _get_module_setting("proxmox_hosts", "pbs_remote_id", "")
    if not pbs_remote_id:
        raise ValueError("Kein PBS-Remote konfiguriert — bitte in den Einstellungen von 'Proxmox Hosts' auswählen")
    remote = get_remote(pbs_remote_id)
    if not remote:
        raise ValueError(f"PBS-Remote '{pbs_remote_id}' nicht gefunden")
    host        = remote.get("host", "")
    token_id    = remote.get("api_token_id", "")
    token_sec   = remote.get("api_token_secret", "")
    datastore   = remote.get("pbs_datastore", "")
    fingerprint = remote.get("pbs_fingerprint", "")
    if not host or not token_id or not datastore:
        raise ValueError(
            f"PBS-Remote '{host}': host, api_token_id und pbs_datastore müssen konfiguriert sein"
        )
    return {
        "repository":  f"{token_id}@{host}:{datastore}",
        "password":    token_sec,
        "fingerprint": fingerprint,
    }


def _get_proxmox_host_info(entry: dict) -> tuple[str, str, int]:
    if not entry.get("remote_id"):
        raise ValueError("Job nicht konfiguriert: 'remote_id' fehlt")
    from astrapi_backup.modules.remotes.engine import get_remote_ssh
    try:
        return get_remote_ssh(entry["remote_id"])
    except ValueError as e:
        log("ERROR", str(e))
        raise


def preview(item_id) -> list[dict]:
    """Gibt den Befehl zurück, der bei run_single ausgeführt würde."""
    entry = _get_entry(_get_config(), item_id)
    if not entry:
        return []

    try:
        host, ssh_user, ssh_port = _get_proxmox_host_info(entry)
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    try:
        pbs = _get_pbs_config(entry)
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    connection = build_connection_string(host, ssh_user)

    pxar_sources = _default_sources()
    pxar_sources += entry.get("source", [])

    ssh_connect_timeout = _get_global_setting("ssh_connect_timeout", 10)
    namespace           = "host"

    cmd_parts = [
        f"PBS_REPOSITORY={pbs['repository']}", "PBS_PASSWORD=***", "PBS_FINGERPRINT=***",
        "sudo", "--preserve-env=PBS_REPOSITORY,PBS_PASSWORD,PBS_FINGERPRINT",
        "/usr/bin/proxmox-backup-client", "backup", *pxar_sources,
        "--backup-type", "host", "--backup-id", "$(hostname)",
        "--ns", namespace, "--backup-time", "$(date +%s)",
    ]
    cmd_str = " ".join(cmd_parts)

    if connection == "local":
        full_cmd = cmd_str
    else:
        full_cmd = f"ssh -o BatchMode=yes -o ConnectTimeout={ssh_connect_timeout} {connection} '{cmd_str}'"

    return [{"label": "proxmox-backup-client", "cmd": full_cmd}]


def run():
    from astrapi.core.modules.scheduler.job_runner import run_all
    run_all("proxmox_hosts", _get_config(), run_single)


def run_single(item_id, entry=None):
    if entry is None:
        entry = _get_entry(_get_config(), item_id) or {}
    with log_context("proxmox_hosts", item_id):
        try:
            host, ssh_user, ssh_port = _get_proxmox_host_info(entry)
        except ValueError as e:
            log("ERROR", str(e))
            return

        try:
            pbs = _get_pbs_config(entry)
        except ValueError as e:
            log("ERROR", str(e))
            return

        log("INFO", f"=== Host '{entry.get('description', host)}' gestartet ===")
        if not require_hosts([host], user=ssh_user):
            return
        status = _backup(host, ssh_user, entry, pbs)
        from datetime import datetime
        _patch_item("proxmox_hosts", item_id,
                    last_run=datetime.now().strftime("%d.%m.%Y %H:%M"),
                    last_status=status)
        log("INFO", f"=== Host '{entry.get('description', host)}' abgeschlossen ===")


def _backup(host, ssh_user: str, entry, pbs: dict) -> str:
    connection = build_connection_string(host, ssh_user)

    pxar_sources = _default_sources()
    pxar_sources += entry.get("source", [])

    ssh_connect_timeout = _get_global_setting("ssh_connect_timeout", 10)

    env = dict(os.environ)
    env["PBS_REPOSITORY"] = pbs["repository"]
    env["PBS_PASSWORD"]   = pbs["password"]
    env["PBS_FINGERPRINT"] = pbs["fingerprint"]

    namespace = "host"
    base_cmd = [
        "sudo", "--preserve-env=PBS_REPOSITORY,PBS_PASSWORD,PBS_FINGERPRINT",
        "/usr/bin/proxmox-backup-client", "backup", *pxar_sources,
        "--backup-type", "host", "--backup-id", "$(hostname)",
        "--ns", namespace, "--backup-time", "$(date +%s)"
    ]

    if is_local(host):
        cmd = base_cmd
    else:
        cmd = [
            f"PBS_REPOSITORY={env['PBS_REPOSITORY']}",
            f"PBS_PASSWORD={env['PBS_PASSWORD']}",
            f"PBS_FINGERPRINT={env['PBS_FINGERPRINT']}",
            *base_cmd
        ]

    try:
        run_cmd(cmd, connection, env=env, ssh_connect_timeout=ssh_connect_timeout)
        log("INFO", f"Host-Backup '{host}' erfolgreich")
        return "ok"
    except subprocess.CalledProcessError as e:
        log("WARNING", f"Host-Backup '{host}' fehlgeschlagen")
        log("ERROR", e.stderr.strip() if e.stderr else "Unbekannter Fehler.")
        return "error"
