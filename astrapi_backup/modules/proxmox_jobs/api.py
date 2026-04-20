# modules/proxmox_jobs/api.py
from pathlib import Path

from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_jobs.jobs import preview as _preview, KEY, _PBS_PORT

router = make_htmx_crud_router(KEY, Path(__file__).parent / "schema.yaml", preview_fn=_preview, running_fn=get_running, create_defaults={"last_status": "neu"})


def fetch_available_jobs() -> list[dict]:
    """Gibt PBS-Jobs aller proxmox_host-Remotes zurück, die noch nicht registriert sind.

    Fragt je Remote verify-job, sync-job und prune-job ab und filtert
    bereits eingetragene (remote_id, type, job)-Kombinationen heraus.
    """
    import requests
    import urllib3
    import logging
    from astrapi_core.system.db import load_config
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select, get_remote

    _log = logging.getLogger(__name__)

    registered = {
        (str(e.get("remote_id", "")), e.get("type", ""), e.get("job", ""))
        for e in load_config(KEY).values()
    }

    result = []
    for remote in get_all_remotes_for_select(type_filter="proxmox_backup"):
        if remote["id"] == "local":
            continue
        host = remote.get("host", "")
        if not host:
            continue
        remote_id  = str(remote["id"])
        remote_obj = get_remote(remote_id) or {}

        token_id     = remote_obj.get("api_token_id", "").strip()
        token_secret = remote_obj.get("api_token_secret", "").strip()
        if not token_id or not token_secret:
            _log.warning("fetch_available_jobs: Remote '%s' (%s) hat keinen API-Token konfiguriert – übersprungen", remote_id, host)
            continue

        verify_ssl = str(remote_obj.get("api_verify_ssl", False)).lower() in ("1", "true", "on", "yes")
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {"Authorization": f"PBSAPIToken={token_id}:{token_secret}"}

        for job_type in ("verify", "sync", "prune"):
            url = f"https://{host}:{_PBS_PORT}/api2/json/admin/{job_type}"
            from astrapi_core.system.paths import is_debug
            if is_debug():
                _log.warning("fetch_available_jobs: curl -sk -H 'Authorization: %s' %s", headers.get("Authorization", ""), url)
            try:
                resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
                resp.raise_for_status()
                jobs = resp.json().get("data", [])
            except Exception as exc:
                _log.warning("fetch_available_jobs: %s %s → %s", job_type, url, exc)
                continue

            for job in jobs:
                job_id = job.get("id", "")
                if not job_id:
                    continue
                if (remote_id, job_type, job_id) in registered:
                    continue
                result.append({
                    "job":       job_id,
                    "type":      job_type,
                    "remote_id": remote_id,
                    "host":      host,
                    "store":     job.get("store", ""),
                    "schedule":  job.get("schedule", ""),
                })

    result.sort(key=lambda x: (x["type"], x["job"]))
    return result
