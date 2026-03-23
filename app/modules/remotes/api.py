# app/modules/remotes/api.py
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Header

from core.system.db import load_config, get_item, delete_item, save_item, next_item_id

KEY = "remotes"
router = APIRouter(tags=[KEY])


def _list_response(request: Request):
    from core.ui.fastapi_templates import get_templates
    return get_templates().TemplateResponse(
        "partials/list_wrapper_inner.html",
        {
            "request":          request,
            "cfg":              load_config(KEY),
            "module":           KEY,
            "content_template": f"{KEY}/partials/list.html",
            "container_id":     f"tab-{KEY}",
            "loading_id":       f"{KEY}-loading",
        },
    )


@router.post("/create")
async def create_one(request: Request):
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    new_id = next_item_id(KEY)
    save_item(KEY, new_id, payload)
    try:
        from .jobs import register_item_actions
        register_item_actions(new_id, payload)
    except Exception:
        pass
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return payload


@router.patch("/{item_id}/edit")
async def patch_one(item_id: str, request: Request):
    iid      = int(item_id)
    existing = get_item(KEY, iid)
    if existing is None:
        raise HTTPException(404, "Item not found")
    form    = await request.form()
    payload = dict(form)
    payload["enabled"] = payload.get("enabled") in ("on", "1", True)
    existing.update(payload)
    save_item(KEY, iid, existing)
    try:
        from .jobs import register_item_actions
        register_item_actions(iid, existing)
    except Exception:
        pass
    if request.headers.get("HX-Request") == "true":
        return _list_response(request)
    return existing


@router.delete("/{item_id}/delete")
def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
    if not delete_item(KEY, item_id):
        raise HTTPException(404, "Item not found")
    try:
        from .jobs import unregister_item_actions
        unregister_item_actions(item_id)
    except Exception:
        pass
    if hx_request:
        return _list_response(request)


@router.post("/{item_id}/toggle")
def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
    cfg = load_config(KEY)
    key = item_id
    if key not in cfg:
        try:
            key = int(item_id)
        except ValueError:
            pass
    cfg[key]["enabled"] = not cfg[key].get("enabled", False)
    save_item(KEY, key, cfg[key])
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "item": key, "enabled": cfg[key]["enabled"]}


@router.post("/{item_id}/wake")
def wake_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
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
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "mac": mac}


@router.post("/{item_id}/shutdown")
def shutdown_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
    item = get_item(KEY, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    host     = item.get("host", "")
    ssh_user = item.get("ssh_user")
    if not host:
        raise HTTPException(400, "Kein Hostname konfiguriert")
    try:
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             f"{ssh_user}@{host}", "sudo shutdown -h now"],
            check=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"SSH-Verbindung zu {host} hat das Timeout überschritten")
    except subprocess.CalledProcessError as ex:
        raise HTTPException(500, f"Shutdown fehlgeschlagen: {ex}")
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "host": host}


@router.post("/{item_id}/scan-host-key")
def scan_host_key(request: Request, item_id: str, hx_request: str | None = Header(None)):
    item = get_item(KEY, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    host = item.get("host", "")
    if not host:
        raise HTTPException(400, "Kein Hostname konfiguriert")
    ssh_port = item.get("ssh_port", 22)
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    known_hosts.parent.mkdir(mode=0o700, exist_ok=True)
    try:
        keyscan_cmd = ["ssh-keyscan", "-H", "-p", str(ssh_port), host]
        result = subprocess.run(keyscan_cmd, capture_output=True, text=True, timeout=15)
        if not result.stdout.strip():
            raise HTTPException(500, f"ssh-keyscan lieferte keine Ausgabe für {host} – Host erreichbar?")
        with open(known_hosts, "a") as f:
            f.write(result.stdout)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"ssh-keyscan Timeout für {host}")
    except OSError as ex:
        raise HTTPException(500, f"known_hosts konnte nicht geschrieben werden: {ex}")
    if hx_request:
        return _list_response(request)
    return {"status": "ok", "host": host}


@router.get("/for-select")
def remotes_for_select():
    """Returns all enabled remotes for job form dropdowns"""
    from .engine import get_all_remotes_for_select
    return {"options": get_all_remotes_for_select()}
