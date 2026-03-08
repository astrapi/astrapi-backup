"""core/modules/settings/__init__.py – Framework-Einstellungen Modul."""

from app.modules._base import AstrapiModule
from .ui import bp

module = AstrapiModule(
    key          = "settings",
    label        = "Einstellungen",
    icon         = "settings",
    nav_group    = "System",
    ui_blueprint = bp,
)
