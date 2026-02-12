from fastapi import APIRouter
from ..storage import load_config

router = APIRouter(prefix="/rsync", tags=["rsync"])

@router.get("/")
def get_rsync_config():
    return load_config("rsync")
