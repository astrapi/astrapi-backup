# app/modules/remotes/jobs.py
"""Scheduler-Aktionen für das Remotes-Modul.

Jeder Eintrag registriert drei eigene Aktionen:
  remotes.wake.<id>     – Magic Packet senden
  remotes.wait.<id>     – warten bis Gerät per SSH erreichbar ist
  remotes.poweroff.<id> – SSH-Shutdown

Hilfsfunktionen:
  register_item_actions(item_id, entry)   – Aktionen für einen Eintrag anmelden
  unregister_item_actions(item_id)        – Aktionen für einen Eintrag abmelden
  sync_all_item_actions()                 – alle DB-Einträge neu synchronisieren
"""
import subprocess
import time
import logging

log = logging.getLogger(__name__)


def _get_config():
    from core.system.db import load_config
    return load_config("remotes")


# ── Einzelaktionen ─────────────────────────────────────────────────────────────

def wake_single(item_id):
    """Sendet ein Wake-on-LAN Magic Packet an einen bestimmten Eintrag."""
    from core.system.db import get_item
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


def wait_for_single(item_id, timeout: int = 300, interval: int = 10):
    """Blockiert bis das Remote-Gerät per SSH erreichbar ist (oder Timeout abläuft)."""
    from core.system.db import get_item
    from core.system.reachability import check_ssh
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
    deadline = time.monotonic() + timeout
    log.info("Remote '%s' (%s): warte auf SSH-Erreichbarkeit (max %ds) …", desc, host, timeout)
    while time.monotonic() < deadline:
        if check_ssh(host, ssh_user):
            log.info("Remote '%s' (%s): erreichbar", desc, host)
            return
        time.sleep(interval)
    log.error("Remote '%s' (%s): nach %ds nicht erreichbar – Timeout", desc, host, timeout)


def poweroff_single(item_id):
    """Fährt ein bestimmtes Remote-Gerät per SSH herunter."""
    from core.system.db import get_item
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
    """Registriert die Scheduler-Aktionen für ein Remote-Gerät."""
    try:
        from core.modules.scheduler.engine import register_action
        iid  = str(item_id)
        desc = entry.get("host") or f"Remote #{iid}"
        if not entry.get("mac", "").strip():
            return
        register_action(
            f"remotes.wake.{iid}",
            f"{desc}: Starten (WoL)",
            lambda _id=iid: wake_single(_id),
            source="remotes",
            source_label="Remote-Geräte",
        )
        register_action(
            f"remotes.wait.{iid}",
            f"{desc}: Warten bis erreichbar",
            lambda _id=iid: wait_for_single(_id),
            source="remotes",
            source_label="Remote-Geräte",
        )
        register_action(
            f"remotes.poweroff.{iid}",
            f"{desc}: Herunterfahren",
            lambda _id=iid: poweroff_single(_id),
            source="remotes",
            source_label="Remote-Geräte",
        )
    except Exception as e:
        log.debug("Remotes: Scheduler-Aktionen für '%s' nicht registriert: %s", item_id, e)


def unregister_item_actions(item_id) -> None:
    """Entfernt die Scheduler-Aktionen eines Remote-Geräts aus der Registry."""
    try:
        from core.modules.scheduler.engine import _actions
        iid = str(item_id)
        _actions.pop(f"remotes.wake.{iid}",     None)
        _actions.pop(f"remotes.wait.{iid}",     None)
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
