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

from astrapi_core.system.logger import log, log_context

_logger = logging.getLogger(__name__)


def _get_config():
    from astrapi_core.system.db import load_config
    return load_config("remotes")


# ── Einzelaktionen ─────────────────────────────────────────────────────────────
# Alle drei geben "ok"/"error" zurueck (T-055): vorher fiel bei jedem Fehler
# (Eintrag fehlt, kein Host konfiguriert, SSH-Timeout, wakeonlan fehlgeschlagen)
# die Funktion einfach durch und gab implizit None zurueck - fuer den Scheduler
# ununterscheidbar von Erfolg. Job-Status, Benachrichtigung ("abgeschlossen"
# statt "fehlgeschlagen") und Activity-Log waren dadurch falsch. Nachfolgende
# Steps im selben Job werden dadurch weiterhin nicht gestoppt (siehe G-018) -
# nur der gemeldete Status ist jetzt wahrheitsgemaess. Ausserdem log_context()
# + core.system.log() statt logging.getLogger(), damit die Meldungen im
# Activity-Log der App landen statt nur im Server-Journal (analog borg/rsync).

def wake_single(item_id):
    """Sendet ein Wake-on-LAN Magic Packet an einen bestimmten Eintrag."""
    from astrapi_core.system.db import get_item
    with log_context("remotes", item_id):
        entry = get_item("remotes", item_id)
        if entry is None:
            log("ERROR", f"Remote-Gerät '{item_id}' nicht gefunden")
            return "error"
        mac  = entry.get("mac", "").strip()
        desc = entry.get("host", str(item_id))
        if not mac:
            log("WARNING", f"Remote '{desc}': keine MAC-Adresse konfiguriert")
            return "error"
        try:
            subprocess.run(["wakeonlan", mac], check=True, timeout=10)
            log("INFO", f"Remote '{desc}' ({mac}): Magic Packet gesendet")
            return "ok"
        except FileNotFoundError:
            log("ERROR", f"Remote '{desc}': wakeonlan nicht gefunden – bitte installieren")
            return "error"
        except subprocess.CalledProcessError as ex:
            log("ERROR", f"Remote '{desc}': Wake-on-LAN fehlgeschlagen: {ex}")
            return "error"


def wait_for_single(item_id, timeout: int = 300, interval: int = 10):
    """Blockiert bis das Remote-Gerät per SSH erreichbar ist (oder Timeout abläuft)."""
    from astrapi_core.system.db import get_item
    from astrapi_core.system.reachability import check_ssh
    with log_context("remotes", item_id):
        entry = get_item("remotes", item_id)
        if entry is None:
            log("ERROR", f"Remote-Gerät '{item_id}' nicht gefunden")
            return "error"
        host     = entry.get("host", "").strip()
        ssh_user = entry.get("ssh_user") or "root"
        ssh_port = entry.get("ssh_port")
        desc     = entry.get("host", str(item_id))
        if not host:
            log("WARNING", f"Remote '{desc}': kein Hostname konfiguriert")
            return "error"
        deadline = time.monotonic() + timeout
        log("INFO", f"Remote '{desc}' ({host}): warte auf SSH-Erreichbarkeit (max {timeout}s) …")
        while time.monotonic() < deadline:
            if check_ssh(host, ssh_user, ssh_port=ssh_port):
                log("INFO", f"Remote '{desc}' ({host}): erreichbar")
                return "ok"
            time.sleep(interval)
        log("ERROR", f"Remote '{desc}' ({host}): nach {timeout}s nicht erreichbar – Timeout")
        return "error"


def poweroff_single(item_id):
    """Fährt ein bestimmtes Remote-Gerät per SSH herunter."""
    from astrapi_core.system.db import get_item
    with log_context("remotes", item_id):
        entry = get_item("remotes", item_id)
        if entry is None:
            log("ERROR", f"Remote-Gerät '{item_id}' nicht gefunden")
            return "error"
        host     = entry.get("host", "").strip()
        ssh_user = entry.get("ssh_user") or "root"
        ssh_port = entry.get("ssh_port")
        desc     = entry.get("host", str(item_id))
        if not host:
            log("WARNING", f"Remote '{desc}': kein Hostname konfiguriert")
            return "error"
        poweroff_cmd = entry.get("poweroff_cmd") or "sudo shutdown -h now"
        ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
        if ssh_port and int(ssh_port) != 22:
            ssh_cmd += ["-p", str(ssh_port)]
        ssh_cmd += [f"{ssh_user}@{host}", poweroff_cmd]
        try:
            subprocess.run(ssh_cmd, check=True, timeout=30)
            log("INFO", f"Remote '{desc}' ({ssh_user}@{host}): Shutdown-Befehl gesendet")
            return "ok"
        except subprocess.TimeoutExpired:
            log("ERROR", f"Remote '{desc}': SSH-Verbindung zu {host} hat das Timeout überschritten")
            return "error"
        except subprocess.CalledProcessError as ex:
            log("ERROR", f"Remote '{desc}': Poweroff fehlgeschlagen: {ex}")
            return "error"


# ── Scheduler-Registrierung ────────────────────────────────────────────────────

def register_item_actions(item_id, entry: dict) -> None:
    """Registriert die Scheduler-Aktionen für ein Remote-Gerät."""
    try:
        from astrapi_core.modules.scheduler.engine import register_action
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
        _logger.debug("Remotes: Scheduler-Aktionen für '%s' nicht registriert: %s", item_id, e)


def unregister_item_actions(item_id) -> None:
    """Entfernt die Scheduler-Aktionen eines Remote-Geräts aus der Registry."""
    try:
        from astrapi_core.modules.scheduler.engine import _actions
        iid = str(item_id)
        _actions.pop(f"remotes.wake.{iid}",     None)
        _actions.pop(f"remotes.wait.{iid}",     None)
        _actions.pop(f"remotes.poweroff.{iid}", None)
    except Exception as e:
        _logger.debug("Remotes: Scheduler-Aktionen für '%s' nicht abgemeldet: %s", item_id, e)


def sync_all_item_actions() -> None:
    """Registriert die Aktionen aller vorhandenen Remote-Geräte (beim Start)."""
    try:
        for item_id, entry in _get_config().items():
            register_item_actions(item_id, entry)
    except Exception as e:
        _logger.debug("Remotes: Sync der Scheduler-Aktionen fehlgeschlagen: %s", e)
