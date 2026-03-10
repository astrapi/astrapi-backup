from core.ui import Module
from .api import router
from .ui import bp

module = Module(
    key          = "wol",
    label        = "Wake on LAN",
    icon         = "monitor",
    api_router   = router,
    ui_blueprint = bp,
)
