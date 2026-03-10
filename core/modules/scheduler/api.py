# core/modules/scheduler/api.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/config")
def get_config():
    from core.modules.scheduler.engine import get_config as _get
    return _get()


@router.post("/config")
async def update_config(request_data: dict):
    from core.modules.scheduler.engine import update_config as _update
    return _update(
        cron=request_data.get("cron"),
        enabled=request_data.get("enabled"),
    )


@router.post("/trigger")
def trigger(debug: bool = False):
    from core.modules.scheduler.engine import trigger_now, is_configured
    if not is_configured():
        return JSONResponse({"ok": False, "error": "Scheduler nicht konfiguriert"}, status_code=503)
    trigger_now(debug=debug)
    return {"ok": True}
