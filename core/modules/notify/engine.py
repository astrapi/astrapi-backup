# core/modules/notify/engine.py
"""Benachrichtigungs-Engine - Multi-Channel-Architektur.

Beim Aufruf von send() werden alle passenden aktiven Kanaele benachrichtigt.

Nutzung:
    from core.modules.notify import engine as notify
    notify.send("Backup fertig", "web-01 gesichert", event=notify.SUCCESS)
    notify.send("Host down",    "web-01 nicht erreichbar", event=notify.WARNING, source="hosts")

Quelle registrieren (in __init__.py des Moduls):
    from core.modules.notify.engine import register_source
    register_source("hosts", "Hosts")

Eigenes Backend registrieren (in main.py, vor App-Start):
    from core.modules.notify.engine import register_backend, BaseNotifier

    class TelegramNotifier(BaseNotifier):
        def __init__(self, bot_token, chat_id):
            self.bot_token = bot_token
            self.chat_id   = chat_id
        def send(self, title, message, priority="default", tags=None) -> bool:
            ...

    register_backend(
        "telegram",
        lambda cfg: TelegramNotifier(
            bot_token = cfg.get("tg_token", ""),
            chat_id   = cfg.get("tg_chat_id", ""),
        )
    )
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Ereignis-Konstanten

SUCCESS = "success"
ERROR   = "error"
WARNING = "warning"
INFO    = "info"

_PRIORITY_MAP: dict[str, str] = {
    SUCCESS: "default",
    INFO:    "low",
    WARNING: "high",
    ERROR:   "urgent",
}

_TAG_MAP: dict[str, list[str]] = {
    SUCCESS: ["white_check_mark"],
    INFO:    ["information_source"],
    WARNING: ["warning"],
    ERROR:   ["rotating_light"],
}


class BaseNotifier(ABC):
    """Abstrakte Basisklasse fuer Benachrichtigungs-Backends."""

    @abstractmethod
    def send(
        self,
        title:    str,
        message:  str,
        priority: str       = "default",
        tags:     list[str] = None,
    ) -> bool:
        """Sendet eine Benachrichtigung. Returns True bei Erfolg."""
        ...


class NotifyEngine:
    """Kapselt Backend-Registry und Source-Registry der Benachrichtigungs-Engine.

    Kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        # Backend-Registry: key -> factory(channel_dict) -> BaseNotifier
        self._backends: dict[str, Callable[[dict], BaseNotifier]] = {}
        # Source-Registry: key -> label (Anzeigename in der Kanal-UI)
        self._sources: dict[str, str] = {}

    def reset(self) -> None:
        """Setzt den internen Zustand zurück (für Test-Isolation)."""
        self._backends = {}
        self._sources = {}

    def register_source(self, key: str, label: str) -> None:
        """Registriert eine Benachrichtigungsquelle (Modul) fuer die Kanal-UI.

        Args:
            key:   Eindeutiger Quellen-Schluessel, z.B. "hosts" oder "job-abc123".
            label: Anzeigename in der Kanal-Konfiguration, z.B. "Hosts".
        """
        self._sources[key] = label

    def unregister_source(self, key: str) -> None:
        """Entfernt eine Benachrichtigungsquelle aus der Registry."""
        self._sources.pop(key, None)

    def get_registered_sources(self) -> dict[str, str]:
        """Gibt {key: label} aller registrierten Quellen zurueck."""
        return dict(self._sources)

    def register_backend(self, key: str, factory: Callable[[dict], BaseNotifier]) -> None:
        """Registriert ein benutzerdefiniertes Backend.

        Args:
            key:     Eindeutiger Backend-Schluessel (erscheint in der Kanal-UI).
            factory: Callable(channel_config_dict) -> BaseNotifier-Instanz.
        """
        self._backends[key] = factory

    def get_registered_backends(self) -> list[str]:
        """Gibt alle zusaetzlich registrierten Backend-Keys zurueck (ohne eingebaute)."""
        return list(self._backends.keys())

    def _notifier_for_channel(self, channel: dict) -> Optional[BaseNotifier]:
        """Erstellt den passenden Notifier fuer einen Kanal-Config-Dict."""
        backend_key = channel.get("backend", "ntfy")

        factory = self._backends.get(backend_key)
        if factory is not None:
            try:
                return factory(channel)
            except Exception as e:
                log.error("notify: Factory fuer Backend '%s' fehlgeschlagen: %s", backend_key, e)
                return None

        if backend_key == "ntfy":
            from .backends.ntfy import NtfyNotifier
            return NtfyNotifier(
                url   = channel.get("ntfy_url",   "https://ntfy.sh") or "https://ntfy.sh",
                topic = channel.get("ntfy_topic", "") or "",
                token = channel.get("ntfy_token") or None,
            )

        if backend_key == "email":
            from .backends.email import EmailNotifier
            return EmailNotifier(
                smtp_host            = channel.get("mail_smtp_host", "localhost") or "localhost",
                smtp_port            = int(channel.get("mail_smtp_port") or 587),
                smtp_user            = channel.get("mail_smtp_user", "") or "",
                smtp_password        = channel.get("mail_smtp_password", "") or "",
                smtp_tls             = bool(channel.get("mail_smtp_tls", True)),
                mail_from            = channel.get("mail_from", "") or "",
                mail_to              = channel.get("mail_to", "") or "",
                mail_subject_prefix  = channel.get("mail_subject_prefix", "[Notify]") or "[Notify]",
            )

        log.warning("notify: Unbekanntes Backend '%s' - Kanal wird uebersprungen", backend_key)
        return None

    def send(
        self,
        title:    str,
        message:  str,
        event:    str           = INFO,
        source:   Optional[str] = None,
        tags:     list[str]     = None,
        priority: Optional[str] = None,
    ) -> int:
        """Sendet ueber alle aktiven Jobs, die zum Ereignistyp und zur Quelle passen.

        Die Engine iteriert zuerst ueber Notify-Jobs (Ereignis- und Quellenfilter),
        sucht dann den verknuepften Kanal heraus und sendet ueber dessen Backend.

        Args:
            title:    Titel der Benachrichtigung.
            message:  Nachrichtentext.
            event:    Ereignistyp (INFO, SUCCESS, WARNING, ERROR).
            source:   Quellenkennung des sendenden Moduls, z.B. "hosts" oder "scheduler".
                      Jobs mit konfiguriertem sources-Filter empfangen nur passende Quellen.
                      None = allgemeine Nachricht, wird von allen Jobs empfangen.
            tags:     Zusaetzliche Tags fuer das Backend (z.B. ntfy-Emojis).
            priority: Ueberschreibt die automatische Prioritaet des Ereignistyps.

        Returns:
            Anzahl der erfolgreich benachrichtigten Kanaele.
        """
        try:
            from .storage import store, job_store
            channels = store.list()
            jobs     = job_store.list()
        except Exception as e:
            log.debug("notify: Storage nicht verfuegbar: %s", e)
            return 0

        if not jobs:
            return 0

        eff_priority = priority or _PRIORITY_MAP.get(event, "default")
        eff_tags     = list(tags or []) + _TAG_MAP.get(event, [])
        sent         = 0

        for job_id, job in jobs.items():
            if not job.get("enabled", False):
                continue
            job_events = job.get("events") or []
            if event not in job_events:
                continue
            job_sources = job.get("sources") or []
            if job_sources and source is not None and source not in job_sources:
                continue

            channel_id = job.get("channel_id", "")
            channel    = channels.get(channel_id)
            if channel is None:
                log.warning("notify: Job '%s' verweist auf unbekannten Kanal '%s'", job_id, channel_id)
                continue
            if not channel.get("enabled", False):
                continue

            notifier = self._notifier_for_channel(channel)
            if notifier is None:
                continue

            try:
                ok = notifier.send(title, message, eff_priority, eff_tags)
                if ok:
                    sent += 1
                    log.debug("notify: '%s' via Job '%s' (Kanal '%s') gesendet", title, job_id, channel_id)
                else:
                    log.warning("notify: Job '%s' (Kanal '%s') lieferte Fehler fuer '%s'", job_id, channel_id, title)
            except Exception as e:
                log.error("notify: Job '%s' (Kanal '%s') Fehler beim Senden: %s", job_id, channel_id, e)

        return sent

    def test_channel(self, channel_id: str) -> tuple[bool, str]:
        """Sendet eine Testbenachrichtigung direkt ueber einen bestimmten Kanal."""
        try:
            from .storage import store
            channel = store.get(channel_id)
        except Exception as e:
            return False, f"Storage-Fehler: {e}"

        if channel is None:
            return False, f"Kanal '{channel_id}' nicht gefunden."

        notifier = self._notifier_for_channel(channel)
        if notifier is None:
            return False, f"Backend '{channel.get('backend', '?')}' nicht verfügbar."

        try:
            ok = notifier.send(
                title    = "Testbenachrichtigung",
                message  = "Benachrichtigungen sind korrekt konfiguriert",
                priority = "default",
                tags     = ["bell"],
            )
            if ok:
                return True, "Testbenachrichtigung erfolgreich gesendet."
            return False, "Backend lieferte einen Fehler (kein HTTP 2xx)."
        except Exception as e:
            return False, str(e)

    def test_job(self, job_id: str) -> tuple[bool, str]:
        """Sendet eine Testbenachrichtigung ueber den Kanal eines bestimmten Jobs."""
        try:
            from .storage import store, job_store
            job     = job_store.get(job_id)
            if job is None:
                return False, f"Job '{job_id}' nicht gefunden."
            channel_id = job.get("channel_id", "")
            channel    = store.get(channel_id)
        except Exception as e:
            return False, f"Storage-Fehler: {e}"

        if channel is None:
            return False, f"Kanal '{channel_id}' nicht gefunden (Job '{job_id}')."

        notifier = self._notifier_for_channel(channel)
        if notifier is None:
            return False, f"Backend '{channel.get('backend', '?')}' nicht verfügbar."

        try:
            ok = notifier.send(
                title    = "Testbenachrichtigung",
                message  = f"Job '{job.get('label', job_id)}' ist korrekt konfiguriert",
                priority = "default",
                tags     = ["bell"],
            )
            if ok:
                return True, "Testbenachrichtigung erfolgreich gesendet."
            return False, "Backend lieferte einen Fehler (kein HTTP 2xx)."
        except Exception as e:
            return False, str(e)


# Modul-level Singleton
_engine = NotifyEngine()


# ── Shims (halten alle bestehenden Aufrufstellen kompatibel) ───────────────────

def register_source(key: str, label: str) -> None:
    """Registriert eine Benachrichtigungsquelle (Modul) fuer die Kanal-UI.

    Args:
        key:   Eindeutiger Quellen-Schluessel, z.B. "hosts" oder "job-abc123".
        label: Anzeigename in der Kanal-Konfiguration, z.B. "Hosts".
    """
    _engine.register_source(key, label)


def unregister_source(key: str) -> None:
    """Entfernt eine Benachrichtigungsquelle aus der Registry."""
    _engine.unregister_source(key)


def get_registered_sources() -> dict[str, str]:
    """Gibt {key: label} aller registrierten Quellen zurueck."""
    return _engine.get_registered_sources()


def register_backend(key: str, factory: Callable[[dict], BaseNotifier]) -> None:
    """Registriert ein benutzerdefiniertes Backend.

    Args:
        key:     Eindeutiger Backend-Schluessel (erscheint in der Kanal-UI).
        factory: Callable(channel_config_dict) -> BaseNotifier-Instanz.
    """
    _engine.register_backend(key, factory)


def get_registered_backends() -> list[str]:
    """Gibt alle zusaetzlich registrierten Backend-Keys zurueck (ohne eingebaute)."""
    return _engine.get_registered_backends()


def send(
    title:    str,
    message:  str,
    event:    str           = INFO,
    source:   Optional[str] = None,
    tags:     list[str]     = None,
    priority: Optional[str] = None,
) -> int:
    """Sendet ueber alle aktiven Jobs, die zum Ereignistyp und zur Quelle passen.

    Die Engine iteriert zuerst ueber Notify-Jobs (Ereignis- und Quellenfilter),
    sucht dann den verknuepften Kanal heraus und sendet ueber dessen Backend.

    Args:
        title:    Titel der Benachrichtigung.
        message:  Nachrichtentext.
        event:    Ereignistyp (INFO, SUCCESS, WARNING, ERROR).
        source:   Quellenkennung des sendenden Moduls, z.B. "hosts" oder "scheduler".
                  Jobs mit konfiguriertem sources-Filter empfangen nur passende Quellen.
                  None = allgemeine Nachricht, wird von allen Jobs empfangen.
        tags:     Zusaetzliche Tags fuer das Backend (z.B. ntfy-Emojis).
        priority: Ueberschreibt die automatische Prioritaet des Ereignistyps.

    Returns:
        Anzahl der erfolgreich benachrichtigten Kanaele.
    """
    return _engine.send(title, message, event, source, tags, priority)


def test_channel(channel_id: str) -> tuple[bool, str]:
    """Sendet eine Testbenachrichtigung direkt ueber einen bestimmten Kanal."""
    return _engine.test_channel(channel_id)


def test_job(job_id: str) -> tuple[bool, str]:
    """Sendet eine Testbenachrichtigung ueber den Kanal eines bestimmten Jobs."""
    return _engine.test_job(job_id)


# Rückwärtskompatibilität
test = test_channel
