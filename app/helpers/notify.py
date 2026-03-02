import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def notify_ntfy(message: str, priority: str | None = None):
    """Sendet eine ntfy-Benachrichtigung. NTFY_URL aus SQLite-Settings."""
    if not message or not message.strip():
        return
    from api.storage import get_setting
    url = get_setting("ntfy_url", "")
    if not url:
        return
    headers = {}
    if priority:
        headers["Priority"] = priority
    try:
        requests.post(url, data=message.encode("utf-8"),
                      headers=headers, verify=False, timeout=5)
    except Exception as e:
        print(f"Fehler beim Senden an ntfy: {e}")
