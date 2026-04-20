# app/modules/remotes/ui.py
import subprocess
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.store import SqliteTableStore
from astrapi_core.ui.render import render

KEY    = "remotes"
_DIR   = Path(__file__).parent
store  = SqliteTableStore(KEY)

router = make_crud_router(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    has_run_buttons=False,
    has_status=False,
    description_field="host",
    extra_page_actions_template=f"{KEY}/partials/page_actions.html",
    extra_actions_template=f"{KEY}/partials/extra_actions.html",
)


# ── Modulspezifische Extrarouten ──────────────────────────────────────────────

@router.get(f"/ui/{KEY}/{{item}}/wake", response_class=HTMLResponse)
def wake_modal(item: str, request: Request):
    container_id = request.query_params.get("container_id", f"tab-{KEY}")
    loading_id   = request.query_params.get("loading_id",   f"{KEY}-loading")
    description  = request.query_params.get("description", item)
    return render(request, "partials/confirm_modal.html", dict(
        description=description, verb="aufwecken (Wake on LAN)",
        confirm_url=f"/api/{KEY}/{item}/wake",
        method="post",
        container_id=container_id, loading_id=loading_id,
    ))



@router.get(f"/ui/{KEY}/{{item}}/shutdown", response_class=HTMLResponse)
def shutdown_modal(item: str, request: Request):
    container_id = request.query_params.get("container_id", f"tab-{KEY}")
    loading_id   = request.query_params.get("loading_id",   f"{KEY}-loading")
    description  = request.query_params.get("description", item)
    return render(request, "partials/confirm_modal.html", dict(
        description=description, verb="herunterfahren",
        subject="dieses Gerät",
        confirm_url=f"/api/{KEY}/{item}/shutdown",
        method="post",
        container_id=container_id, loading_id=loading_id,
    ))


@router.get(f"/ui/{KEY}/check-ssh-modal", response_class=HTMLResponse)
def check_ssh_modal(request: Request):
    return render(request, f"{KEY}/modals/ssh_check_results.html", {})


@router.get(f"/ui/{KEY}/check-ssh-spinner", response_class=HTMLResponse)
def check_ssh_spinner(request: Request):
    return render(request, f"{KEY}/partials/ssh_check_spinner.html", {})


@router.get(f"/ui/{KEY}/{{item}}/power-modal", response_class=HTMLResponse)
def power_modal(item: str, request: Request):
    from astrapi_core.system.db import get_item
    entry = get_item(KEY, item) or {}
    return render(request, f"{KEY}/modals/power_check.html", {
        "item_id": item,
        "host":    entry.get("host", item),
    })


@router.post(f"/ui/{KEY}/{{item}}/power", response_class=HTMLResponse)
def power_action(item: str, request: Request):
    from astrapi_core.system.db import get_item
    entry = get_item(KEY, item)
    if not entry:
        return HTMLResponse("", status_code=404)
    host     = (entry.get("host") or "").strip()
    ssh_user = (entry.get("ssh_user") or "root").strip()
    ssh_port = str(entry.get("ssh_port") or 22)
    reachable = False
    if host:
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 "-o", "StrictHostKeyChecking=no",
                 "-p", ssh_port, f"{ssh_user}@{host}", "echo ok"],
                capture_output=True, text=True, timeout=8,
            )
            reachable = r.returncode == 0 and "ok" in r.stdout
        except subprocess.TimeoutExpired:
            reachable = False
    if reachable:
        return render(request, f"{KEY}/partials/power_confirm.html", dict(
            verb="ausschalten",
            btn_style="danger",
            confirm_url=f"/api/{KEY}/{item}/shutdown",
            method="post",
        ))
    return render(request, f"{KEY}/partials/power_confirm.html", dict(
        verb="einschalten",
        btn_style="primary",
        confirm_url=f"/api/{KEY}/{item}/wake",
        method="post",
    ))


@router.post(f"/ui/{KEY}/check-ssh-all", response_class=HTMLResponse)
def check_ssh_all(request: Request):
    results = []
    for item_id, entry in store.list().items():
        if not entry.get("enabled"):
            continue
        host     = (entry.get("host") or "").strip()
        ssh_user = (entry.get("ssh_user") or "root").strip()
        ssh_port = str(entry.get("ssh_port") or 22)
        if not host:
            results.append({"host": f"#{item_id}", "user": "—", "ok": None, "error": "Kein Hostname"})
            continue
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 "-o", "StrictHostKeyChecking=no",
                 "-p", ssh_port, f"{ssh_user}@{host}", "echo ok"],
                capture_output=True, text=True, timeout=8,
            )
            ok = r.returncode == 0 and "ok" in r.stdout
            error = r.stderr.strip().splitlines()[0] if not ok and r.stderr.strip() else None
        except subprocess.TimeoutExpired:
            ok, error = False, "Timeout"
        results.append({"host": host, "user": ssh_user, "ok": ok, "error": error})
    return render(request, f"{KEY}/partials/ssh_check_table.html", {"results": results})
