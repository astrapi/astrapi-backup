from fastapi import APIRouter
from ..storage import load_config

router = APIRouter(prefix="/proxmox", tags=["proxmox"])

@router.get("/jobs/")
def get_proxmox_jobs_config():
    return load_config("proxmox_jobs")

@router.get("/lxc/")
def get_proxmox_lxc_config():
    return load_config("proxmox_lxc")

@router.get("/hosts/")
def get_proxmox_hosts_config():
    return load_config("proxmox_hosts")