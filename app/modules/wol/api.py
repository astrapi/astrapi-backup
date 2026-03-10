# app/modules/wol/api.py
# Wake-on-LAN – Einstellungen speichern
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["wol"])


@router.post("/settings", response_class=HTMLResponse)
async def save_wol_settings(request: Request):
    form    = await request.form()
    macs    = [v.strip() for v in form.getlist("wol_mac")  if v.strip()]
    hosts   = [v.strip() for v in form.getlist("wol_host") if v.strip()]
    entries = [{"mac": m, "host": h} for m, h in zip(macs, hosts)]
    from core.ui.settings_registry import set_module
    set_module("wol", "entries", entries)
    return HTMLResponse('<span style="color:var(--g);">✔ Gespeichert</span>')
