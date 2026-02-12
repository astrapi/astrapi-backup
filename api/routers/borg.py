# api/routers/borg.py
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator, constr
from ..storage import load_config, get_item, delete_item, save_item
from .config import create_router

router = APIRouter(prefix="/borg", tags=["borg"])


@router.get("/")
def get_borg_config():
    return load_config("borg")


@router.get("/{item_id}", summary="Get single borg item")
def get_borg_item(item_id: str):
    item = get_item("borg", item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


class BorgUpdate(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[constr(strip_whitespace=True, min_length=1)] = None
    source_host: Optional[constr(strip_whitespace=True, min_length=1)] = None
    source_path: Optional[constr(strip_whitespace=True, min_length=1)] = None
    target_host: Optional[constr(strip_whitespace=True, min_length=1)] = None
    target_path: Optional[constr(strip_whitespace=True, min_length=1)] = None
    pre: Optional[List[constr(strip_whitespace=True, min_length=1)]] = None
    post: Optional[List[constr(strip_whitespace=True, min_length=1)]] = None
    # optional container for arbitrary additional keys (kept separate)
    extra: Optional[Dict[str, Any]] = None

    @validator("pre", "post", each_item=True)
    def non_empty_commands(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("commands in pre/post must be non-empty strings")
        return v

    @validator("source_path", "target_path")
    def path_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("path must not be empty")
        return v

    @validator("description")
    def description_not_too_long(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > 1000:
            raise ValueError("description too long")
        return v


@router.patch("/{item_id}", summary="Partially update a borg item")
def patch_borg_item(item_id: str, payload: BorgUpdate):
    """
    Partielles Update: payload ist ein BorgUpdate Model.
    Nur die gesetzten Felder werden übernommen (shallow merge).
    """
    existing = get_item("borg", item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Item not found")

    # Nur tatsächlich gelieferte Felder übernehmen
    update_data: Dict[str, Any] = payload.dict(exclude_unset=True)

    # Falls 'extra' genutzt wurde, entpacke dessen Inhalte in update_data
    extra = update_data.pop("extra", None)
    if extra:
        if not isinstance(extra, dict):
            raise HTTPException(status_code=400, detail="extra must be an object/dict")
        # merge extra keys (they may override explicit fields if same name)
        update_data.update(extra)

    if not update_data:
        # nichts zu tun
        return existing

    # Optional: schütze gegen unerwartete Keys (erlaube nur bekannte Felder)
    allowed_fields = {
        "enabled",
        "description",
        "source_host",
        "source_path",
        "target_host",
        "target_path",
        "pre",
        "post",
    }
    unknown = set(update_data.keys()) - allowed_fields
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields in payload: {sorted(list(unknown))}")

    # Speichere/merge das Item (save_item macht ein shallow-merge)
    save_item("borg", item_id, update_data)

    updated = get_item("borg", item_id)
    return updated


@router.delete("/{item_id}", summary="Delete single borg item", status_code=204)
def delete_borg_item(item_id: str):
    ok = delete_item("borg", item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
