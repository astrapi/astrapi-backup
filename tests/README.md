# Test-Uebersicht

Diese Tests sind in drei Ebenen aufgeteilt:

## 1. Unit-Tests

Ziel:
Schnelle Tests fuer reine Logik ohne Webserver, Datenbank oder echte externe Prozesse.

Dateien:
- tests/unit/test_version.py
- tests/unit/test_borg_api_helpers.py
- tests/unit/test_module_loading.py

Aktuell getestet:
- Lesen von Versionsnummern aus version.yaml
- Default-Verhalten bei fehlenden Dateien
- Bereinigung und Validierung von Pfaden
- Aufbau von Verzeichnis- und Dateiansichten
- Bereinigung von Formular-Payloads
- Umwandlung von Listenfeldern wie pre_0, pre_1 in Python-Listen
- Laden aller registrierten App- und Core-Module
- Grundlegende Modul-Registry-Abdeckung

## 2. API-Integrationstests

Ziel:
Pruefen, ob FastAPI-Routen korrekt auf Requests reagieren und Eingaben richtig verarbeiten.

Dateien:
- tests/integration/api/test_all_module_api_routes.py
- tests/integration/api/test_borg_api_routes.py

Aktuell getestet:
- App-CRUD-Routen fuer borg, rsync, proxmox_hosts, proxmox_jobs, proxmox_lxc und remotes
- Borg-Preview-Route
- Remotes Wake- und Shutdown-Endpunkte
- History- und Errors-HTML-Endpunkte
- Sysinfo-Endpunkte
- Notify-Kanal-API und Notify-Job-API
- Scheduler-API

Geprueft wird dabei insbesondere:
- Statuscode
- Umwandlung von Form-Daten
- enabled-Logik
- Aufruf der Speicherfunktionen mit den erwarteten Werten
- Rueckgabe von HTML- und JSON-Antworten fuer Core-Module
- Toggle-, Delete-, Trigger- und Test-Endpunkte

Hinweis:
Diese Tests verwenden keinen echten Browser und keine echten Borg-Kommandos. Externe Abhaengigkeiten werden kontrolliert ersetzt.

## 3. UI-Integrationstests

Ziel:
Pruefen, ob Flask-UI-Routen das erwartete HTML fuer Modals und Formulare liefern.

Dateien:
- tests/integration/ui/test_all_module_ui_routes.py
- tests/integration/ui/test_borg_ui_modals.py

Aktuell getestet:
- Content-Routen fuer App-Module und Core-Module
- CRUD-Modals fuer borg, rsync, proxmox_hosts, proxmox_jobs, proxmox_lxc und remotes
- Zusatzmodals fuer remotes (wake, shutdown)
- Notify-Kanal- und Notify-Job-Modals
- Scheduler-Modals und Scheduler-Form-Aktionen
- Settings-, Sysinfo-, History- und Errors-Views

Geprueft wird dabei insbesondere:
- Modal wird als HTML geliefert
- Formular-Markup ist vorhanden
- Titel und Inhalte des Modals stimmen
- API-Ziel-URLs fuer Aktionen sind korrekt eingebettet
- Listen- und Tab-Views rendern fuer alle registrierten Module
- Formular-POSTs liefern die erwarteten HTML-Antworten

Wichtig:
Diese Tests bestaetigen, dass die UI-Routen korrektes HTML zurueckgeben. Sie simulieren keinen echten Klick im Browser und pruefen kein JavaScript oder HTMX im laufenden DOM.

## Was aktuell noch nicht getestet wird

- Echte End-to-End-Browserinteraktionen
- HTMX-Austausch im Browser
- JavaScript-Verhalten im Frontend
- Echte Borg-Aufrufe ueber subprocess
- Vollstaendige End-to-End-Kette mit realer Datenbank und UI zusammen
- Langlaufende Scheduler-, SSH- und Wake-on-LAN-Aktionen gegen echte Zielsysteme

## Tests ausfuehren

Gesamte Testsuite:

```bash
python -m pytest
```

Nur Unit-Tests:

```bash
python -m pytest tests/unit
```

Nur API-Tests:

```bash
python -m pytest tests/integration/api
```

Nur UI-Tests:

```bash
python -m pytest tests/integration/ui
```

## Struktur

```text
tests/
  conftest.py
  README.md
  unit/
    test_module_loading.py
    test_borg_api_helpers.py
    test_version.py
  integration/
    api/
      test_all_module_api_routes.py
      test_borg_api_routes.py
    ui/
      test_all_module_ui_routes.py
      test_borg_ui_modals.py
```

## Empfehlung fuer weitere Ausbaustufen

Sinnvolle naechste Schritte:
- Fehlerfaelle und 4xx/5xx-Wege fuer weitere API-Routen testen
- E2E-Browsertests fuer echte Klickpfade ergaenzen
- Datenbanknahe Integrationstests mit separater Test-DB einfuehren