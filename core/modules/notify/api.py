# core/modules/notify/api.py
"""FastAPI-Router für /api/notify/ – Kanal- und Job-CRUD + Test-Endpunkte."""

from fastapi import APIRouter, HTTPException

from .storage import store, job_store, KEY
from .schema import ChannelIn, JobIn

router = APIRouter()


# ── Kanäle ────────────────────────────────────────────────────────────────────

@router.get("/", summary="Kanäle auflisten")
def list_channels():
    items = store.list()
    return {"channels": items, "total": len(items)}


@router.get("/{channel_id}", summary="Kanal abrufen")
def get_channel(channel_id: str):
    item = store.get(channel_id)
    if item is None:
        raise HTTPException(404, f"Kanal '{channel_id}' nicht gefunden")
    return item


@router.post("/", summary="Kanal erstellen", status_code=201)
def create_channel(channel_id: str, item: ChannelIn):
    try:
        return {"created": channel_id, "channel": store.create(channel_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(409, str(e))


@router.put("/{channel_id}", summary="Kanal aktualisieren")
def update_channel(channel_id: str, item: ChannelIn):
    try:
        return {"updated": channel_id, "channel": store.update(channel_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/{channel_id}/toggle", summary="Kanal aktivieren/deaktivieren")
def toggle_channel(channel_id: str):
    try:
        return {"channel_id": channel_id, "enabled": store.toggle(channel_id, default=False)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/{channel_id}", summary="Kanal löschen", status_code=204)
def delete_channel(channel_id: str):
    try:
        store.delete(channel_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/{channel_id}/test", summary="Testbenachrichtigung über Kanal senden")
def test_channel_api(channel_id: str):
    from .engine import test_channel
    ok, msg = test_channel(channel_id)
    return {"ok": ok, "message": msg}


# ── Notify-Jobs ───────────────────────────────────────────────────────────────

@router.get("/jobs/", summary="Jobs auflisten")
def list_jobs():
    items = job_store.list()
    return {"jobs": items, "total": len(items)}


@router.get("/jobs/{job_id}", summary="Job abrufen")
def get_job(job_id: str):
    item = job_store.get(job_id)
    if item is None:
        raise HTTPException(404, f"Job '{job_id}' nicht gefunden")
    return item


@router.post("/jobs/", summary="Job erstellen", status_code=201)
def create_job(job_id: str, item: JobIn):
    try:
        return {"created": job_id, "job": job_store.create(job_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(409, str(e))


@router.put("/jobs/{job_id}", summary="Job aktualisieren")
def update_job(job_id: str, item: JobIn):
    try:
        return {"updated": job_id, "job": job_store.update(job_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/jobs/{job_id}/toggle", summary="Job aktivieren/deaktivieren")
def toggle_job(job_id: str):
    try:
        return {"job_id": job_id, "enabled": job_store.toggle(job_id, default=False)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/jobs/{job_id}", summary="Job löschen", status_code=204)
def delete_job(job_id: str):
    try:
        job_store.delete(job_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/jobs/{job_id}/test", summary="Testbenachrichtigung über Job senden")
def test_job_api(job_id: str):
    from .engine import test_job
    ok, msg = test_job(job_id)
    return {"ok": ok, "message": msg}
