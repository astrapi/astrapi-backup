from pathlib import Path
from core.ui.module_loader import load_modul
from .runner import run, run_single  # re-export fuer api/routers/run.py
from .api import router
from .ui import bp

module = load_modul(Path(__file__).parent, "proxmox_hosts", router, bp)
