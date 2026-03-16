def notify_ntfy(message: str, priority: str | None = None):
    """Sendet eine Benachrichtigung über die Notify-Engine (alle konfigurierten Kanäle)."""
    if not message or not message.strip():
        return
    try:
        from core.modules.notify import engine
        engine.send(
            title    = "BackupCtl",
            message  = message,
            event    = engine.INFO,
            source   = "backup",
            tags     = ([f"priority:{priority}"] if priority else []),
        )
    except Exception as e:
        print(f"Fehler beim Senden der Benachrichtigung: {e}")
