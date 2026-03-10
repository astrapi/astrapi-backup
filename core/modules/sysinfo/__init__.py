"""core/modules/sysinfo/__init__.py – System-Informationen Modul."""

from app.modules._base import AstrapiModule
from .api import router
from .ui import bp

module = AstrapiModule(
    key          = "sysinfo",
    label        = "System",
    icon         = "monitor",
    api_router   = router,
    ui_blueprint = bp,
    nav_group    = "System",
)
