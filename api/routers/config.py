# api/routers/config.py
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Body, Response, status, Request, Header
from fastapi.templating import Jinja2Templates
from ..storage import load_config, get_item, delete_item, save_item
from ui.schema_loader import load_schema

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
    async def patch_one(item_id: str, request: Request):
        item_id = int(item_id)

        form = await request.form()
        payload = dict(form)

        existing = get_item(storage_key, item_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Item not found")

        # Checkbox normalisieren
        payload["enabled"] = payload.get("enabled") == "on"

        # Listenfelder extrahieren
        pre = []
        post = []

        for key, value in payload.items():
            if key.startswith("pre_"):
                index = int(key.split("_")[1])
                pre.append((index, value))
            elif key.startswith("post_"):
                index = int(key.split("_")[1])
                post.append((index, value))

        pre = [v for _, v in sorted(pre)]
        post = [v for _, v in sorted(post)]

        # pre_*/post_* entfernen
        payload = {k: v for k, v in payload.items() if not k.startswith(("pre_", "post_"))}

        # Schema laden
        schema = load_schema(storage_key)

        # Felder, die im Formular fehlen → leere Strings
        for field in schema:
            name = field["name"]
            if name not in payload:
                payload[name] = ""

        # Merge-Patch
        existing.update(payload)
        existing["pre"] = pre
        existing["post"] = post

        # Cleanup
        existing = clean_empty_fields(existing)

        save_item(storage_key, item_id, existing)

        # HTMX → Tab neu rendern
        if request.headers.get("HX-Request") == "true":
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

        return existing



    def clean_empty_fields(data: dict) -> dict:
        cleaned = {}
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            if isinstance(value, list) and len(value) == 0:
                continue
            cleaned[key] = value
        return cleaned




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
