# modules/proxmox_jobs.py
import time
import urllib.parse

import requests
import urllib3

from astrapi.core.system.logger import log, log_context
from astrapi_backup.api.storage import load_config as _load_config, get_entry as _get_entry, patch_item as _patch_item

KEY = "proxmox_jobs"
_PBS_PORT = 8007

def _get_config(): return _load_config(KEY)


def _get_host(entry: dict) -> str:
    """Ermittelt den PBS-Host aus dem Remote-Eintrag."""
    from astrapi_backup.modules.remotes.engine import get_remote
    remote_id = entry.get("remote_id")
    if not remote_id:
        raise ValueError("Job hat keine remote_id konfiguriert")
    remote = get_remote(remote_id)
    if not remote:
        raise ValueError(f"Remote Device '{remote_id}' nicht gefunden")
    if not remote.get("enabled"):
        raise ValueError(f"Remote Device '{remote_id}' ist deaktiviert")
    host = remote.get("host")
    if not host:
        raise ValueError(f"Remote Device '{remote_id}': Kein Host konfiguriert")
    return host


def _api_token_for_remote(remote: dict) -> tuple[str, str]:
    token_id     = remote.get("api_token_id", "").strip()
    token_secret = remote.get("api_token_secret", "").strip()
    if not token_id or not token_secret:
        raise ValueError(f"API-Token für Remote '{remote.get('host')}' nicht konfiguriert")
    return token_id, token_secret


def _verify_ssl_for_remote(remote: dict) -> bool:
    return str(remote.get("api_verify_ssl", False)).lower() in ("1", "true", "on", "yes")


def _auth_headers(token_id: str, token_secret: str) -> dict:
    return {"Authorization": f"PBSAPIToken={token_id}:{token_secret}"}


def _parse_upid_node(upid: str) -> str:
    """Extrahiert den Node-Namen aus dem UPID-Format: UPID:{node}:{...}"""
    parts = upid.split(":")
    if len(parts) >= 2 and parts[0] == "UPID":
        return parts[1]
    raise ValueError(f"Ungültiges UPID-Format: {upid!r}")


def _trigger_job(host: str, job_type: str, job_name: str, remote: dict) -> str:
    """Startet den PBS-Job via API. Gibt den UPID zurück."""
    token_id, token_secret = _api_token_for_remote(remote)
    verify_ssl = _verify_ssl_for_remote(remote)
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url  = f"https://{host}:{_PBS_PORT}/api2/json/admin/{job_type}/{job_name}/run"
    from astrapi.core.system.paths import is_debug
    if is_debug():
        log("INFO", f"curl -sk -X POST -H 'Authorization: PBSAPIToken={token_id}:<secret>' '{url}'")
    resp = requests.post(url, headers=_auth_headers(token_id, token_secret),
                         json={}, verify=verify_ssl, timeout=30)
    resp.raise_for_status()
    upid = resp.json().get("data", "")
    if not upid:
        raise ValueError(f"PBS API: kein UPID in der Antwort für {job_type}/{job_name}")
    return upid


def _wait_for_task(host: str, upid: str, remote: dict,
                   poll_interval: int = 5, timeout: int = 3600) -> str:
    """Pollt den Task-Status bis er abgeschlossen ist. Gibt exitstatus zurück."""
    token_id, token_secret = _api_token_for_remote(remote)
    verify_ssl = _verify_ssl_for_remote(remote)
    headers    = _auth_headers(token_id, token_secret)

    node     = _parse_upid_node(upid)
    upid_enc = urllib.parse.quote(upid, safe="")
    url      = f"https://{host}:{_PBS_PORT}/api2/json/nodes/{node}/tasks/{upid_enc}/status"

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=15)
        resp.raise_for_status()
        data   = resp.json().get("data", {})
        status = data.get("status", "")
        if status == "stopped":
            return data.get("exitstatus", "unknown")
        time.sleep(poll_interval)
    raise TimeoutError(f"Task {upid} nicht innerhalb von {timeout}s abgeschlossen")


def preview(item_id) -> list[dict]:
    """Gibt den API-Aufruf zurück, der bei run_single ausgeführt würde."""
    job = _get_entry(_get_config(), item_id)
    if job is None:
        return []

    job_name = job.get("job")
    job_type = job.get("type")
    if not job_name or not job_type:
        return []

    try:
        host = _get_host(job)
    except ValueError as e:
        return [{"label": "Error", "cmd": str(e)}]

    try:
        from astrapi_backup.modules.remotes.engine import get_remote
        remote_obj = get_remote(job["remote_id"]) if job.get("remote_id") else {}
        token_id = remote_obj.get("api_token_id", "").strip() or "<api-token-id>"
    except Exception:
        token_id = "<pbs-token-id>"

    url = f"https://{host}:{_PBS_PORT}/api2/json/admin/{job_type}/{job_name}/run"
    cmd = (
        f"curl -k -X POST "
        f"-H 'Authorization: PBSAPIToken={token_id}:<secret>' "
        f"'{url}'"
    )
    return [{"label": f"{job_type}-job (PBS API)", "cmd": cmd}]


def run():
    from astrapi.core.modules.scheduler.job_runner import run_all
    run_all(KEY, _get_config(), run_single,
            desc_fn=lambda iid, e: e.get("job", iid))


def run_by_type(job_type: str):
    """Führt alle aktivierten Jobs eines bestimmten Typs sequenziell aus."""
    from astrapi.core.modules.scheduler.job_runner import run_all
    filtered = {iid: e for iid, e in _get_config().items() if e.get("type") == job_type}
    run_all(KEY, filtered, run_single,
            desc_fn=lambda iid, e: e.get("job", iid))


def run_single(item_id, job=None):
    if job is None:
        job = _get_entry(_get_config(), item_id)
    if job is None:
        log("ERROR", f"Proxmox-Job '{item_id}' nicht gefunden")
        return
    with log_context(KEY, item_id):
        job_name = job.get("job")
        job_type = job.get("type")
        if not job_name or not job_type:
            log("ERROR", f"Proxmox-Job '{item_id}': Pflichtfelder (job, type) fehlen")
            return

        try:
            from astrapi_backup.modules.remotes.engine import get_remote
            remote_obj = get_remote(job.get("remote_id")) or {}
            host = _get_host(job)
        except ValueError as e:
            log("ERROR", str(e))
            return

        log("INFO", f"=== Job '{job_name}' ({job_type}) gestartet ===")
        last_status = "ERROR"
        try:
            upid = _trigger_job(host, job_type, job_name, remote_obj)
            log("INFO", f"{job_type}-job '{job_name}': Task gestartet ({upid})")
            exitstatus = _wait_for_task(host, upid, remote_obj)
            if exitstatus == "OK":
                last_status = "OK"
                log("INFO", f"{job_type}-job '{job_name}' auf '{host}' erfolgreich")
            else:
                last_status = exitstatus
                log("WARNING", f"{job_type}-job '{job_name}' auf '{host}' abgeschlossen mit Status: {exitstatus}")
        except Exception as e:
            log("WARNING", f"{job_type}-job '{job_name}' auf '{host}' fehlgeschlagen")
            log("ERROR", str(e))

        from datetime import datetime
        _patch_item(KEY, item_id, last_run=datetime.now().strftime("%d.%m.%Y %H:%M"), last_status=last_status)
        log("INFO", f"=== Job '{job_name}' abgeschlossen ===")
