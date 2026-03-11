# app/modules/remotes/jobs.py
"""Scheduler-Aktionen für das Remotes-Modul.

Jeder Eintrag registriert zwei eigene Aktionen:
  remotes.wake.<id>     – Magic Packet senden
  remotes.poweroff.<id> – SSH-Shutdown

Hilfsfunktionen:
  register_item_actions(item_id, entry)   – Aktionen für einen Eintrag anmelden
  unregister_item_actions(item_id)        – Aktionen für einen Eintrag abmelden
  sync_all_item_actions()                 – alle DB-Einträge neu synchronisieren
"""
import subprocess
import logging

log = logging.getLogger(__name__)


def _get_config():
    from api.storage import load_config
    return load_config("remotes")


# ── Einzelaktionen ─────────────────────────────────────────────────────────────

def wake_single(item_id):
    """Sendet ein Wake-on-LAN Magic Packet an einen bestimmten Eintrag."""
    from api.storage import get_item
    entry = get_item("remotes", item_id)
    if entry is None:
        log.error("Remote-Gerät '%s' nicht gefunden", item_id)
        return
    mac  = entry.get("mac", "").strip()
    desc = entry.get("description", str(item_id))
    if not mac:
        log.warning("Remote '%s': keine MAC-Adresse konfiguriert", desc)
        return
    try:
        subprocess.run(["wakeonlan", mac], check=True, timeout=10)
        log.info("Remote '%s' (%s): Magic Packet gesendet", desc, mac)
    except FileNotFoundError:
        log.error("Remote '%s': wakeonlan nicht gefunden – bitte installieren", desc)
    except subprocess.CalledProcessError as ex:
        log.error("Remote '%s': Wake-on-LAN fehlgeschlagen: %s", desc, ex)


def poweroff_single(item_id):
    """Fährt ein bestimmtes Remote-Gerät per SSH herunter."""
    from api.storage import get_item
    entry = get_item("remotes", item_id)
    if entry is None:
        log.error("Remote-Gerät '%s' nicht gefunden", item_id)
        return
    host     = entry.get("host", "").strip()
    ssh_user = entry.get("ssh_user") or "root"
    desc     = entry.get("description", str(item_id))
    if not host:
        log.warning("Remote '%s': kein Hostname konfiguriert", desc)
        return
    try:
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             f"{ssh_user}@{host}", "sudo shutdown -h now"],
            check=True, timeout=30,
        )
        log.info("Remote '%s' (%s@%s): Shutdown-Befehl gesendet", desc, ssh_user, host)
    except subprocess.TimeoutExpired:
        log.error("Remote '%s': SSH-Verbindung zu %s hat das Timeout überschritten", desc, host)
    except subprocess.CalledProcessError as ex:
        log.error("Remote '%s': Poweroff fehlgeschlagen: %s", desc, ex)


# ── Scheduler-Registrierung ────────────────────────────────────────────────────

def register_item_actions(item_id, entry: dict) -> None:
    """Registriert die beiden Scheduler-Aktionen für ein Remote-Gerät."""
    try:
        from core.modules.scheduler.engine import register_action
        iid  = str(item_id)
        desc = entry.get("description") or f"Remote #{iid}"
        register_action(
            f"remotes.wake.{iid}",
            f"Aufwecken: {desc}",
            lambda _id=iid: wake_single(_id),
            source="remotes",
            source_label="Remote-Geräte",
        )
        register_action(
            f"remotes.poweroff.{iid}",
            f"Herunterfahren: {desc}",
            lambda _id=iid: poweroff_single(_id),
        )
    except Exception as e:
        log.debug("Remotes: Scheduler-Aktionen für '%s' nicht registriert: %s", item_id, e)


def unregister_item_actions(item_id) -> None:
    """Entfernt die Scheduler-Aktionen eines Remote-Geräts aus der Registry."""
    try:
        from core.modules.scheduler.engine import _actions
        iid = str(item_id)
        _actions.pop(f"remotes.wake.{iid}",     None)
        _actions.pop(f"remotes.poweroff.{iid}", None)
    except Exception as e:
        log.debug("Remotes: Scheduler-Aktionen für '%s' nicht abgemeldet: %s", item_id, e)


def sync_all_item_actions() -> None:
    """Registriert die Aktionen aller vorhandenen Remote-Geräte (beim Start)."""
    try:
        for item_id, entry in _get_config().items():
            register_item_actions(item_id, entry)
    except Exception as e:
        log.debug("Remotes: Sync der Scheduler-Aktionen fehlgeschlagen: %s", e)
