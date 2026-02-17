from fastapi import APIRouter, HTTPException, Form
from fastapi.responses import Response
from ..storage import load_config, save_config

router = APIRouter(tags=["actions"])

ALLOWED_MODULES = {"borg", "proxmox_jobs", "proxmox_lxc", "proxmox_hosts", "rsync"}

@router.post("/api/{module}/{item}/toggle")
def toggle_item(module: str, item: str = Form(...)):
    if module not in ALLOWED_MODULES:
        raise HTTPException(status_code=404, detail="Unknown module")

    cfg = load_config(module)

    if item not in cfg:
        raise HTTPException(status_code=404, detail="Item not found")

    # Toggle
    cfg[item].enabled = not cfg[item].enabled

    # Speichern
    save_config(module, cfg)

    # 204 = No Content → HTMX führt danach automatisch hx-get aus
    return Response(status_code=204)
