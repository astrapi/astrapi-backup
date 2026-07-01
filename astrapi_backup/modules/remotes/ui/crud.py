# app/modules/remotes/ui/crud.py
import subprocess
from pathlib import Path

from astrapi_core.system.db import get_item
from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.htmx_crud_router import make_htmx_crud_router
from astrapi_core.ui.render import render
from astrapi_core.ui.store import SqliteTableStore
from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse

KEY = "remotes"
_DIR = Path(__file__).parent.parent
store = SqliteTableStore(KEY)


def _post_process(payload: dict) -> dict:
    if not payload.get("api_token_secret"):
        payload.pop("api_token_secret", None)
    return payload


def _on_create(item_id: str, data: dict) -> None:
    from astrapi_backup.modules.remotes.jobs import register_item_actions

    register_item_actions(item_id, data)


def _on_update(item_id: str, data: dict) -> None:
    from astrapi_backup.modules.remotes.jobs import register_item_actions

    register_item_actions(item_id, data)


def _on_delete(item_id: str) -> None:
    from astrapi_backup.modules.remotes.jobs import unregister_item_actions

    unregister_item_actions(item_id)


api_router = make_htmx_crud_router(
    KEY,
    _DIR / "config" / "schema.yaml",
    post_process=_post_process,
    on_create=_on_create,
    on_update=_on_update,
    on_delete=_on_delete,
)


@api_router.post("/{item_id}/wake")
def wake_item(item_id: str):
    item = get_item(KEY, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    mac = item.get("mac", "")
    if not mac:
        raise HTTPException(400, "Keine MAC-Adresse konfiguriert")
    try:
        subprocess.run(["wakeonlan", mac], check=True, timeout=10)
    except FileNotFoundError:
        raise HTTPException(500, "wakeonlan nicht gefunden – bitte installieren")
    except subprocess.CalledProcessError as ex:
        raise HTTPException(500, f"Wake-on-LAN fehlgeschlagen: {ex}")
    return {"status": "ok", "mac": mac}


@api_router.post("/{item_id}/shutdown")
def shutdown_item(item_id: str):
    item = get_item(KEY, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    host = item.get("host", "")
    ssh_user = item.get("ssh_user")
    if not host:
        raise HTTPException(400, "Kein Hostname konfiguriert")
    try:
        subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                f"{ssh_user}@{host}",
                "sudo shutdown -h now",
            ],
            check=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"SSH-Verbindung zu {host} hat das Timeout überschritten")
    except subprocess.CalledProcessError as ex:
        raise HTTPException(500, f"Shutdown fehlgeschlagen: {ex}")
    return {"status": "ok", "host": host}


@api_router.get("/for-select")
def remotes_for_select(type: str | None = Query(default=None), local: str = Query(default="1")):
    from astrapi_backup.modules.remotes.service import get_all_remotes_for_select

    return {"options": get_all_remotes_for_select(type_filter=type, include_local=local != "0")}


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    has_run_buttons=False,
    has_toggle=False,
    has_status=False,
    description_field="host",
    extra_buttons=[
        {
            "label": "SSH prüfen",
            "url": f"/ui/{KEY}/check-ssh-modal",
            "title": "SSH-Keys aller Hosts prüfen",
        }
    ],
)



@router.get(f"/ui/{KEY}/check-ssh-modal", response_class=HTMLResponse)
def check_ssh_modal(request: Request):
    return render(request, f"{KEY}/dialogs/ssh_check/modal.html", {})


@router.get(f"/ui/{KEY}/check-ssh-spinner", response_class=HTMLResponse)
def check_ssh_spinner(request: Request):
    return render(request, f"{KEY}/dialogs/ssh_check/spinner.html", {})


@router.get(f"/ui/{KEY}/{{item}}/power-modal", response_class=HTMLResponse)
def power_modal(item: str, request: Request):
    entry = get_item(KEY, item) or {}
    if not (entry.get("mac") or "").strip():
        return render(
            request,
            f"{KEY}/dialogs/power/modal.html",
            {"item_id": item, "host": entry.get("host", item), "no_mac": True},
        )
    return render(
        request,
        f"{KEY}/dialogs/power/modal.html",
        {"item_id": item, "host": entry.get("host", item), "no_mac": False},
    )


@router.post(f"/ui/{KEY}/{{item}}/power", response_class=HTMLResponse)
def power_action(item: str, request: Request):
    entry = get_item(KEY, item)
    if not entry:
        return HTMLResponse("", status_code=404)
    host = (entry.get("host") or "").strip()
    ssh_user = (entry.get("ssh_user") or "root").strip()
    ssh_port = str(entry.get("ssh_port") or 22)
    reachable = False
    if host:
        try:
            r = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-p",
                    ssh_port,
                    f"{ssh_user}@{host}",
                    "echo ok",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            reachable = r.returncode == 0 and "ok" in r.stdout
        except subprocess.TimeoutExpired:
            reachable = False
    if reachable:
        return render(
            request,
            "dialog_confirm.html",
            dict(
                title="Host ausschalten",
                description=host or item,
                verb="ausschalten",

                btn_style="danger",
                confirm_url=f"/api/{KEY}/{item}/shutdown",
                method="post",
            ),
        )
    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Host einschalten",
            description=host or item,
            verb="einschalten",
            qualifier="",
            btn_style="primary",
            confirm_url=f"/api/{KEY}/{item}/wake",
            method="post",
        ),
    )


@router.post(f"/ui/{KEY}/check-ssh-all", response_class=HTMLResponse)
def check_ssh_all(request: Request):
    results = []
    for item_id, entry in store.list().items():
        if not entry.get("enabled"):
            continue
        host = (entry.get("host") or "").strip()
        ssh_user = (entry.get("ssh_user") or "root").strip()
        ssh_port = str(entry.get("ssh_port") or 22)
        if not host:
            results.append(
                {"host": f"#{item_id}", "user": "—", "ok": None, "error": "Kein Hostname"}
            )
            continue
        try:
            r = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=5",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-p",
                    ssh_port,
                    f"{ssh_user}@{host}",
                    "echo ok",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            ok = r.returncode == 0 and "ok" in r.stdout
            error = r.stderr.strip().splitlines()[0] if not ok and r.stderr.strip() else None
        except subprocess.TimeoutExpired:
            ok, error = False, "Timeout"
        results.append({"host": host, "user": ssh_user, "ok": ok, "error": error})
    return render(request, f"{KEY}/dialogs/ssh_check/table.html", {"results": results})
