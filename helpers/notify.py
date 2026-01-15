import requests
import urllib3

# Nur diese eine Warnung unterdrücken
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NTFY_URL = "https://ntfy.simpsons.lan/backup-neu"

def notify_ntfy(message: str, priority: str | None = None):
    """
    Sendet eine ntfy-Benachrichtigung.
    Optional kann eine Priority angegeben werden:
    low, default, high, urgent
    """
    if not message or not message.strip(): 
        return

    headers = {}

    if priority:
        headers["Priority"] = priority

    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers=headers,
            verify=False,
            timeout=5
        )
    except Exception as e:
        print(f"Fehler beim Senden an ntfy: {e}")

