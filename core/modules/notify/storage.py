# core/modules/notify/storage.py
"""YamlStorage-Instanzen für Benachrichtigungskanäle und -Jobs."""

from core.ui.storage import YamlStorage

KEY       = "notify"
store     = YamlStorage("notify_channels")   # Backend-Konfigurationen
job_store = YamlStorage("notify_jobs")       # Benachrichtigungs-Jobs
