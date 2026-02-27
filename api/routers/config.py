# api/routers/config.py
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Body, Response, status, Request, Header
from api.templates import templates as _templates_import
from api.routers.run import get_running
from ..storage import load_config, get_item, delete_item, save_item, next_item_id
from ui.schema_loader import load_schema

import uuid

templates = _templates_import


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

def config_router(storage_key: str, tag: Optional[str] = None) -> APIRouter:
    router = APIRouter(tags=[tag] if tag else [storage_key])

    @router.post("/create")
    async def create_one(request: Request):
        form = await request.form()
        payload = dict(form)

        # Checkbox normalisieren
        payload["enabled"] = payload.get("enabled") == "on"

        # Schema laden
        schema = load_schema(storage_key)

        # Listenfelder vorbereiten
        list_fields = [field["name"] for field in schema if field.get("type") == "list"]
        lists = {name: [] for name in list_fields}

        # Listenfelder extrahieren (z.B. source_0, source_1)
        for key, value in payload.items():
            for list_name in list_fields:
                prefix = f"{list_name}_"
                if key.startswith(prefix):
                    index = int(key.split("_")[1])
                    lists[list_name].append((index, value))

        # Listen sortieren und Werte extrahieren
        for name in list_fields:
            lists[name] = [v for _, v in sorted(lists[name])]

        # Listenfelder aus payload entfernen
        payload = {
            k: v for k, v in payload.items()
            if not any(k.startswith(f"{name}_") for name in list_fields)
        }

        # Fehlende Felder aus Schema auffüllen
        for field in schema:
            name = field["name"]
            if name not in payload and field.get("type") != "list":
                payload[name] = ""

        # Listen hinzufügen
        for name in list_fields:
            payload[name] = lists[name]

        # Nächste freie numerische ID
        next_id = next_item_id(storage_key)

        # Cleanup
        payload = clean_empty_fields(payload)

        save_item(storage_key, next_id, payload)

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
                    "running": get_running(),
                }
            )

        return payload





    # @router.get("/")
    # def list_all():
    #     return load_config(storage_key)

    # @router.get("/{item_id}")
    # def get_one(item_id: str):
    #     item = get_item(storage_key, item_id)
    #     if item is None:
    #         raise HTTPException(status_code=404, detail="Item not found")
    #     return item

    # @router.post("/create", summary="Create a new item", status_code=201)
    # def create_one(payload: Dict[str, Any] = Body(...)):
    #     print("Hallo Welt1!")
    #     if not isinstance(payload, dict):
    #         raise HTTPException(status_code=400, detail="Payload must be a JSON object")
    #     item = payload.get("item")
    #     if item is None or not isinstance(item, dict):
    #         raise HTTPException(status_code=400, detail="Payload must contain an 'item' object")

    #     print(payload)

    #     item_id = payload.get("id")
    #     if item_id:
    #         item_id = str(item_id).strip()
    #     else:
    #         item_id = uuid.uuid4().hex

    #     if get_item(storage_key, item_id) is not None:
    #         raise HTTPException(status_code=409, detail="Item already exists")

    #     print("Hallo Welt2!")

    #     save_item(storage_key, item_id, item)

    #     headers = {"Location": f"/api/config/{storage_key}/{item_id}"}
    #     return Response(content="", status_code=status.HTTP_201_CREATED, headers=headers)

    @router.patch("/{item_id}/edit")
    async def patch_one(item_id: str, request: Request):
        item_id = int(item_id)

        form = await request.form()
        payload = dict(form)

        existing = get_item(storage_key, item_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Item not found")

        # Checkbox normalisieren
        payload["enabled"] = payload.get("enabled") == "on"

        # Schema laden – alle Listfelder generisch extrahieren
        schema = load_schema(storage_key)
        list_fields = [field["name"] for field in schema if field.get("type") == "list"]

        lists = {name: [] for name in list_fields}
        for key, value in payload.items():
            for list_name in list_fields:
                if key.startswith(f"{list_name}_"):
                    try:
                        index = int(key[len(list_name)+1:])
                        lists[list_name].append((index, value))
                    except ValueError:
                        pass

        for name in list_fields:
            lists[name] = [v for _, v in sorted(lists[name])]

        # Alle list_*-Schlüssel aus payload entfernen
        list_prefixes = tuple(f"{name}_" for name in list_fields)
        payload = {k: v for k, v in payload.items()
                   if not any(k.startswith(p) for p in list_prefixes)}

        # Felder die im Formular fehlen → leere Strings
        for field in schema:
            name = field["name"]
            if name not in payload and field.get("type") != "list":
                payload[name] = ""

        # Merge-Patch
        existing.update(payload)
        for name in list_fields:
            existing[name] = lists[name]

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
                    "running": get_running(),
                }
            )

        return existing

    @router.delete("/{item_id}/delete")
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
                    "running": get_running(),
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
                    "running": get_running(),
                }
            )


        # Wenn curl → JSON zurückgeben
        return {"status": "ok", "item": key, "enabled": cfg[key]["enabled"]}

    return router
