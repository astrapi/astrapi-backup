# modules/proxmox.py – Wrapper, importiert die drei Teilmodule
from modules.proxmox_lxc   import run as run_lxc,   run_single as run_single_lxc
from modules.proxmox_hosts import run as run_hosts,  run_single as run_single_host
from modules.proxmox_jobs  import run as run_jobs,   run_single as run_single_job

def run():
    run_lxc()
    run_hosts()
    run_jobs()
