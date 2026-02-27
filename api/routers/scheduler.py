# api/routers/scheduler.py
import re
from fastapi import APIRouter, HTTPException, Request
from api.templates import templates
from pathlib import Path
import scheduler.engine as engine

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter(tags=["scheduler"])

VALID_MODULES = {"borg", "rsync", "proxmox"}
CRON_RE = re.compile(r"^(\*|[0-9,\-\*/]+)\s+(\*|[0-9,\-\*/]+)\s+(\*|[0-9,\-\*/]+)\s+(\*|[0-9,\-\*/]+)\s+(\*|[0-9,\-\*/]+)$")


def _validate(cron, modules):
    if not CRON_RE.match(cron.strip()):
        raise HTTPException(422, detail=f"Ungültiger Cron-Ausdruck: '{cron}'")
    bad = set(modules) - VALID_MODULES
    if bad:
        raise HTTPException(422, detail=f"Unbekannte Module: {bad}")


def _job_list_response(request):
    return templates.TemplateResponse(
        "partials/scheduler/job_list.html",
        {"request": request, "jobs": engine.list_jobs(), "running": engine.get_running_jobs()},
    )


@router.get("/jobs")
def list_jobs(request: Request):
    return _job_list_response(request)


@router.post("/jobs", status_code=201)
async def create_job(request: Request):
    form = await request.form()
    modules = [m.strip() for m in form.get("modules", "").split(",") if m.strip()]
    _validate(form.get("cron", ""), modules)
    try:
        engine.create_job(
            job_id=form.get("id", "").strip(),
            description=form.get("description", "").strip(),
            cron=form.get("cron", "").strip(),
            modules=modules,
            enabled=form.get("enabled") == "on",
        )
    except ValueError as e:
        raise HTTPException(409, detail=str(e))
    return _job_list_response(request)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: str, request: Request):
    form = await request.form()
    modules = [m.strip() for m in form.get("modules", "").split(",") if m.strip()]
    kwargs = {k: v for k, v in {
        "description": form.get("description"),
        "cron": form.get("cron"),
        "modules": modules or None,
        "enabled": form.get("enabled") == "on",
    }.items() if v is not None}
    if "cron" in kwargs:
        _validate(kwargs["cron"], kwargs.get("modules", ["borg"]))
    try:
        engine.update_job(job_id, **kwargs)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    return _job_list_response(request)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    if not engine.delete_job(job_id):
        raise HTTPException(404, detail="Job nicht gefunden")
    return _job_list_response(request)


@router.post("/jobs/{job_id}/toggle")
def toggle_job(job_id: str, request: Request):
    try:
        engine.toggle_job(job_id)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    return _job_list_response(request)


@router.post("/jobs/{job_id}/run")
def trigger_job(job_id: str, request: Request, debug: bool = False):
    try:
        engine.trigger_job(job_id, debug=debug)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    return _job_list_response(request)
