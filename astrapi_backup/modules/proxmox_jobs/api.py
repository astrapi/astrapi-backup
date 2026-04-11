# modules/proxmox_jobs/api.py
from pathlib import Path

from astrapi.core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_jobs.jobs import preview as _preview, KEY, _PBS_PORT

router = make_htmx_crud_router(KEY, Path(__file__).parent / "schema.yaml", preview_fn=_preview, running_fn=get_running)


def fetch_available_jobs() -> list[dict]:
    """Gibt PBS-Jobs aller proxmox_host-Remotes zurück, die noch nicht registriert sind.

    Fragt je Remote verify-job, sync-job und prune-job ab und filtert
    bereits eingetragene (remote_id, type, job)-Kombinationen heraus.
    """
    import requests
    import urllib3
    from astrapi.core.system.db import load_config
    from astrapi.core.system.secrets import get_secret_safe
    from astrapi.core.ui.settings_registry import get_module as _get_module_setting
    from astrapi_backup.modules.remotes.engine import get_all_remotes_for_select

    registered = {
        (str(e.get("remote_id", "")), e.get("type", ""), e.get("job", ""))
        for e in load_config(KEY).values()
    }

    token_id     = _get_module_setting(KEY, "pbs_api_token_id", "").strip()
    token_secret = get_secret_safe(f"module.{KEY}.pbs_api_token_secret", "").strip()
    verify_ssl   = str(_get_module_setting(KEY, "pbs_verify_ssl", False)).lower() in ("1", "true", "on", "yes")

    if not token_id or not token_secret:
        return []

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    headers = {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}

    result = []
    for remote in get_all_remotes_for_select(type_filter="proxmox_host"):
        if remote["id"] == "local":
            continue
        host = remote.get("host", "")
        if not host:
            continue
        remote_id = str(remote["id"])

        for job_type in ("verify", "sync", "prune"):
            url = f"https://{host}:{_PBS_PORT}/api2/json/admin/{job_type}-job"
            try:
                resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
                resp.raise_for_status()
                jobs = resp.json().get("data", [])
            except Exception:
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
