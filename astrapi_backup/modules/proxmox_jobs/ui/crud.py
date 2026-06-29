# modules/proxmox_jobs/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.store import SqliteTableStore
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_jobs.jobs import _PBS_PORT
from astrapi_backup.modules.proxmox_jobs.jobs import preview as _preview

KEY = "proxmox_jobs"
_DIR = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_fields(fields: list) -> list:
    return resolve_options_endpoint(fields)


def fetch_available_jobs() -> list[dict]:
    """Gibt PBS-Jobs aller proxmox_host-Remotes zurück, die noch nicht registriert sind.

    Fragt je Remote verify-job, sync-job und prune-job ab und filtert
    bereits eingetragene (remote_id, type, job)-Kombinationen heraus.
    """
    import logging

    import requests
    import urllib3
    from astrapi_core.system.db import load_config

    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select, get_remote

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
        remote_id = str(remote["id"])
        remote_obj = get_remote(remote_id) or {}

        token_id = remote_obj.get("api_token_id", "").strip()
        token_secret = remote_obj.get("api_token_secret", "").strip()
        if not token_id or not token_secret:
            _log.warning(
                "fetch_available_jobs: Remote '%s' (%s) hat keinen API-Token konfiguriert – übersprungen",
                remote_id,
                host,
            )
            continue

        verify_ssl = str(remote_obj.get("api_verify_ssl", False)).lower() in (
            "1",
            "true",
            "on",
            "yes",
        )
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {"Authorization": f"PBSAPIToken={token_id}:{token_secret}"}

        for job_type in ("verify", "sync", "prune"):
            url = f"https://{host}:{_PBS_PORT}/api2/json/admin/{job_type}"
            from astrapi_core.system.paths import is_debug

            if is_debug():
                _log.warning(
                    "fetch_available_jobs: curl -sk -H 'Authorization: %s' %s",
                    headers.get("Authorization", ""),
                    url,
                )
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
                result.append(
                    {
                        "job": job_id,
                        "type": job_type,
                        "remote_id": remote_id,
                        "host": host,
                        "store": job.get("store", ""),
                        "schedule": job.get("schedule", ""),
                    }
                )

    result.sort(key=lambda x: (x["type"], x["job"]))
    return result


# Eigene Routen zuerst registrieren – FastAPI nutzt first-match
router = APIRouter()


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    from astrapi_core.ui.render import render

    return render(
        request,
        "proxmox_jobs/dialogs/create/modal.html",
        dict(
            loading_id=request.query_params.get("loading_id", f"{KEY}-loading"),
        ),
    )


@router.get(f"/ui/{KEY}/available-select", response_class=HTMLResponse)
def available_select(request: Request):
    from astrapi_core.ui.render import render

    available = []
    try:
        available = fetch_available_jobs()
    except Exception:
        pass
    return render(
        request, "proxmox_jobs/dialogs/create/available_select.html", {"available": available}
    )


# Generische CRUD-Routen danach (create wird durch obige Route überschattet)
_crud = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR.parent / "config" / "schema.yaml"),
    has_run_buttons=True,
    has_toggle=False,
    resolve_fields_fn=_resolve_fields,
    running_fn=get_running,
    filters=[
        {
            "param": "last_status",
            "label": "Status",
            "all_label": "Alle Status",
            "options_fn": lambda: [
                {"value": "neu", "label": "Neu"},
                {"value": "ok", "label": "OK"},
                {"value": "error", "label": "Fehler"},
            ],
        },
    ],
)
router.include_router(_crud)

_SCHEMA_PATH = _DIR.parent / "config" / "schema.yaml"
api_router = make_htmx_crud_router(
    KEY,
    _SCHEMA_PATH,
    preview_fn=_preview,
    running_fn=get_running,
    create_defaults={"last_status": "neu"},
)
