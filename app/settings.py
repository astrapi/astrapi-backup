APP_NAME    = "backupctl"
APP_VERSION = "0.82.0"
APP_LANG    = "de"

import os
# Light-Mode: nur Repos, Archiv-Browser, Statistiken – keine Jobs, kein rsync, kein Proxmox
LIGHT_MODE = os.environ.get("BACKUPCTL_LIGHT", "").lower() in ("1", "true", "yes")

APP_LOGO_SVG = '''<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" style="flex-shrink:0">
  <ellipse cx="12" cy="5" rx="9" ry="3"/>
  <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
  <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
</svg>'''
