# api/routers/settings.py
#
# Speicherung:
#   secrets.env  → nur echte Credentials: BORG_PASSPHRASE, PBS_PASSWORD,
#                  PBS_FINGERPRINT, BORG_PASSPHRASE_<id>
#   SQLite       → alles andere: ntfy, wol, repos_base_path, scheduler
#
import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["settings"])


def _ok(msg: str = "Gespeichert") -> HTMLResponse:
    return HTMLResponse(f'<span style="color:var(--g);">✔ {msg}</span>')


# ── Scheduler ─────────────────────────────────────────────────────────────────

@router.post("/scheduler", response_class=HTMLResponse)
async def save_scheduler(request: Request):
    form    = await request.form()
    cron    = form.get("cron", "0 2 * * *").strip()
    enabled = form.get("enabled", "off") == "on"
    from core.modules.scheduler import engine
    engine.update_config(cron=cron, enabled=enabled)
    return _ok()


@router.post("/scheduler/run", response_class=HTMLResponse)
def run_now(request: Request):
    from core.modules.scheduler import engine
    engine.trigger_now(debug=False)
    return _ok("Gestartet")


# ── ntfy – in SQLite, kein Geheimnis ──────────────────────────────────────────

@router.post("/ntfy", response_class=HTMLResponse)
async def save_ntfy(request: Request):
    form  = await request.form()
    url   = form.get("ntfy_url",   "").strip()
    topic = form.get("ntfy_topic", "").strip()
    from api.storage import set_setting
    set_setting("ntfy_server", url)
    set_setting("ntfy_topic",  topic)
    # Vollständige URL für notify.py – ebenfalls in DB
    full = f"{url.rstrip('/')}/{topic}" if url and topic else url
    set_setting("ntfy_url", full)
    return _ok()


# ── Wake on LAN – in SQLite, kein Geheimnis ───────────────────────────────────

@router.post("/wol", response_class=HTMLResponse)
async def save_wol(request: Request):
    form  = await request.form()
    macs  = [v.strip() for v in form.getlist("wol_mac")  if v.strip()]
    hosts = [v.strip() for v in form.getlist("wol_host") if v.strip()]
    entries = [{"mac": m, "host": h} for m, h in zip(macs, hosts)]
    from api.storage import set_setting
    set_setting("wol_entries", json.dumps(entries))
    return _ok()


# ── Repos-Pfad – in SQLite ────────────────────────────────────────────────────

@router.post("/repos-path", response_class=HTMLResponse)
async def save_repos_path(request: Request, repos_base_path: str = Form("")):
    from api.storage import set_setting
    set_setting("repos_base_path", repos_base_path.strip())
    return _ok()


# ── Zugangsdaten – NUR echte Credentials in secrets.env ──────────────────────

@router.post("/secrets", response_class=HTMLResponse)
async def save_secrets(request: Request):
    form   = await request.form()
    fields = {
        "borg_passphrase": "BORG_PASSPHRASE",
        "pbs_password":    "PBS_PASSWORD",
        "pbs_fingerprint": "PBS_FINGERPRINT",
    }
    from helpers.secrets import set_secret
    for form_key, env_key in fields.items():
        val = form.get(form_key, "").strip()
        if val:   # leer lassen = nicht überschreiben
            set_secret(env_key, val)
    return _ok()
