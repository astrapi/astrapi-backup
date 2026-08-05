"""Gemeinsame Auswertung von Proxmox-Task-Ergebnissen.

Die Proxmox-API liefert im Feld ``exitstatus`` eines abgeschlossenen Tasks
einen Freitext. Bekannte Werte:

    OK                     erfolgreich
    WARNINGS: 3            durchgelaufen, mit Warnungen
    job errors             mindestens ein Teilschritt ist fehlgeschlagen
    interrupted by signal  abgebrochen
    <Fehlermeldung>        alles Übrige

Beide Proxmox-Module haben das bisher je eigen und unterschiedlich falsch
ausgewertet: proxmox_lxc stufte jeden Nicht-OK-Status als Warnung ein und
verharmloste damit echte Fehler, proxmox_jobs setzte den Eintrag auf ``error``,
protokollierte aber auf Stufe WARNING (T-057).
"""


def task_status(exitstatus: "str | None") -> str:
    """Bildet einen Proxmox-exitstatus auf ok / warning / error ab.

    Unbekanntes gilt als Fehler: ein Task, dessen Ergebnis wir nicht deuten
    können, darf nicht als erfolgreich oder harmlos durchgehen.
    """
    s = (exitstatus or "").strip()
    if not s:
        return "error"
    if s.upper() == "OK":
        return "ok"
    if "warning" in s.lower():
        return "warning"
    return "error"


def log_level(status: str) -> str:
    """Passende Log-Stufe zu einem Status – damit Eintrag und Log übereinstimmen."""
    return {"ok": "INFO", "warning": "WARNING"}.get(status, "ERROR")
