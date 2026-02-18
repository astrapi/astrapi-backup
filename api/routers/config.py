# api/routers/config.py
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Body, Response, status, Request, Header
from fastapi.templating import Jinja2Templates
from ..storage import load_config, get_item, delete_item, save_item
import uuid

templates = Jinja2Templates(directory="templates")

def config_router(storage_key: str, tag: Optional[str] = None) -> APIRouter:
    router = APIRouter(tags=[tag] if tag else [storage_key])

    @router.get("/")
    def list_all():
        return load_config(storage_key)

    @router.get("/{item_id}")
    def get_one(item_id: str):
        item = get_item(storage_key, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
        return item

    @router.post("/", summary="Create a new item", status_code=201)
    def create_one(payload: Dict[str, Any] = Body(...)):
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")
        item = payload.get("item")
        if item is None or not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Payload must contain an 'item' object")

        item_id = payload.get("id")
        if item_id:
            item_id = str(item_id).strip()
        else:
            item_id = uuid.uuid4().hex

        if get_item(storage_key, item_id) is not None:
            raise HTTPException(status_code=409, detail="Item already exists")

        save_item(storage_key, item_id, item)

        headers = {"Location": f"/api/config/{storage_key}/{item_id}"}
        return Response(content="", status_code=status.HTTP_201_CREATED, headers=headers)

    @router.patch("/{item_id}")
    def patch_one(item_id: str, payload: Dict[str, Any] = Body(...)):
        existing = get_item(storage_key, item_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Item not found")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")
        save_item(storage_key, item_id, payload)
        return get_item(storage_key, item_id)

    @router.delete("/{item_id}")
    def delete_one(request: Request, item_id: str, hx_request: str | None = Header(None)):
        ok = delete_item(storage_key, item_id)

        if not ok:
            raise HTTPException(status_code=404, detail="Item not found")

        # Wenn HTMX → HTML zurückgeben
        if hx_request:
            return templates.TemplateResponse(
                "partials/list_wrapper.html",
                {
                    "request": request,
                    "cfg": load_config(storage_key),
                    "module": storage_key,
                    "content_template": f"partials/lists/{storage_key}.html",
                    "container_id": f"tab-{storage_key}",
                    "loading_id": f"{storage_key}-loading",
                }
            )

    @router.post("/{item_id}/toggle")
    def toggle_item(request: Request, item_id: str, hx_request: str | None = Header(None)):
        cfg = load_config(storage_key)

        key = item_id
        if key not in cfg:
            try:
                key = int(item_id)
            except ValueError:
                pass
        
        # Toggle durchführen
        cfg[key]["enabled"] = not cfg[key].get("enabled", False)
        save_item(storage_key, key, cfg[key])

        # Wenn HTMX → HTML zurückgeben
        if hx_request:
            return templates.TemplateResponse(
                "partials/list_wrapper.html",
                {
                    "request": request,
                    "cfg": load_config(storage_key),
                    "module": storage_key,
                    "content_template": f"partials/lists/{storage_key}.html",
                    "container_id": f"tab-{storage_key}",
                    "loading_id": f"{storage_key}-loading",
                }
            )


        # Wenn curl → JSON zurückgeben
        return {"status": "ok", "item": key, "enabled": cfg[key]["enabled"]}

    return router
