# modules/proxmox_lxc/ui/crud.py
from pathlib import Path

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.field_resolver import resolve_options_endpoint
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.settings_registry import get_module as _get_module
from astrapi_core.ui.store import SqliteTableStore
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_backup.api.routers.run import get_running
from astrapi_backup.modules.proxmox_lxc.jobs import preview as _preview

KEY = "proxmox_lxc"
_DIR = Path(__file__).parent
store = SqliteTableStore(KEY)


def _resolve_node_label(remote_id: str) -> str:
    try:
        from astrapi_backup.modules.remotes.service import get_remote

        r = get_remote(remote_id)
        return r.get("host") or remote_id if r else remote_id
    except Exception:
        return remote_id


def _resolve_fields(fields: list) -> list:
    """Ersetzt options_from_settings und options_endpoint durch echte Werte."""
    result = []
    for field in fields:
        if "options_from_settings" in field:
            settings_key = field["options_from_settings"]
            nodes = _get_module(KEY, settings_key, []) or []
            field = dict(field)
            field["options"] = [{"value": n, "label": n} for n in nodes if n]
            del field["options_from_settings"]
        result.append(field)
    return resolve_options_endpoint(result)


def fetch_available_lxc() -> list[dict]:
    """Returns LXC containers from all proxmox_node remotes not yet registered.

    Uses /cluster/resources?type=vm (cluster-wide) and filters by type==lxc.
    Node names from the response are matched back to configured remotes.
    """
    import logging

    import requests
    import urllib3
    from astrapi_core.system.db import load_config
    from astrapi_core.system.paths import is_debug

    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select, get_remote

    _log = logging.getLogger(__name__)

    registered = {int(e["vmid"]) for e in load_config(KEY).values() if e.get("vmid") is not None}

    # Alle proxmox_node-Remotes mit vollständigen Daten laden
    node_remotes: dict[str, str] = {}  # short_name → remote_id
    remote_objs: dict[str, dict] = {}  # remote_id  → remote_obj
    for r in get_all_remotes_for_select(type_filter="proxmox_node"):
        if r["id"] == "local" or not r.get("host"):
            continue
        rid = str(r["id"])
        remote_obj = get_remote(rid) or {}
        short = r["host"].split(".")[0]
        node_remotes[short] = rid
        remote_objs[rid] = remote_obj

    if not remote_objs:
        return []

    # Ersten Remote mit Token für Cluster-Abfrage verwenden
    cluster_remote = next((ro for ro in remote_objs.values() if ro.get("api_token_id")), None)
    if not cluster_remote:
        return []

    token_id = cluster_remote.get("api_token_id", "").strip()
    token_secret = cluster_remote.get("api_token_secret", "").strip()
    verify_ssl = str(cluster_remote.get("api_verify_ssl", False)).lower() in (
        "1",
        "true",
        "on",
        "yes",
    )

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    host = cluster_remote["host"]
    headers = {"Authorization": f"PVEAPIToken={token_id}={token_secret}"}
    url = f"https://{host}:8006/api2/json/cluster/resources?type=vm"

    if is_debug():
        _log.warning(
            "fetch_available_lxc: curl -sk -H 'Authorization: PVEAPIToken=%s:<secret>' '%s'",
            token_id,
            url,
        )

    try:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=10)
        resp.raise_for_status()
        resources = resp.json().get("data", [])
    except Exception:
        return []

    first_remote_id = next(iter(remote_objs))
    result = []
    for ct in resources:
        if ct.get("type") != "lxc":
            continue
        vmid = int(ct.get("vmid", 0))
        if not vmid or vmid in registered:
            continue
        node_name = ct.get("node", "")
        remote_id = node_remotes.get(node_name, first_remote_id)
        result.append(
            {
                "vmid": vmid,
                "name": ct.get("name", f"CT {vmid}"),
                "status": ct.get("status", ""),
                "node_id": remote_id,
                "node_host": host,
            }
        )

    result.sort(key=lambda x: x["vmid"])
    return result


# Eigene Routen zuerst registrieren – FastAPI nutzt first-match
router = APIRouter()


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_modal(request: Request):
    from astrapi_core.ui.render import render

    return render(
        request,
        "proxmox_lxc/dialogs/create/modal.html",
        dict(
            loading_id=request.query_params.get("loading_id", f"{KEY}-loading"),
        ),
    )


@router.get(f"/ui/{KEY}/available-select", response_class=HTMLResponse)
def available_select(request: Request):
    from astrapi_core.ui.render import render

    available = []
    try:
        available = fetch_available_lxc()
    except Exception:
        pass
    return render(
        request, "proxmox_lxc/dialogs/create/available_select.html", {"available": available}
    )


@router.post(f"/ui/{KEY}/check-availability")
def check_availability_route(request: Request):
    """Prüft alle konfigurierten LXC auf Existenz im Proxmox-Cluster (ohne
    Backup auszulösen) und leitet danach auf die normale, paginierte
    Content-Route weiter -- kein Backup-Trigger, nur Status-Refresh."""
    from fastapi.responses import RedirectResponse

    from astrapi_backup.modules.proxmox_lxc.jobs import check_availability

    try:
        check_availability()
    except Exception:
        pass
    return RedirectResponse(f"/ui/{KEY}/content", status_code=303)


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
            "param": "node",
            "label": "Node",
            "all_label": "Alle Nodes",
            "options_fn": lambda: [
                {"value": node, "label": _resolve_node_label(node)}
                for node in sorted(
                    {item.get("node") for item in store.list().values() if item.get("node")}
                )
            ],
        },
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
