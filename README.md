# backupctl

Web-UI zur zentralen Verwaltung von Backup-Jobs (Borg, Rsync, Proxmox, Remote-Geräte).

## Dokumentation

- Deutsche Benutzeranleitung: [Benutzeranleitung.md](Benutzeranleitung.md)

## Voraussetzungen

- Python >= 3.11
- `astrapi-core` (lokales Repo, muss parallel geklont sein)

### Systemabhängigkeiten

```bash
apt install borgbackup wakeonlan openssh-client
```

> Borg wird unter `/var/lib/backupadm/.venv/bin/borg` erwartet.

## Setup nach dem Klonen

1. Virtuelles Environment erstellen und aktivieren:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. `astrapi-core` installieren (liegt als Schwesterprojekt neben diesem Repo):

```bash
pip install -e ../astrapi-core
```

3. `backupctl` selbst installieren:

```bash
pip install -e .
```

## Starten

```bash
backupctl --work-dir data --port 9999
```

**Mit Auto-Reload (Entwicklung):**

```bash
backupctl --work-dir data --port 9999 --reload
```

| Parameter    | Standard    | Beschreibung                            |
|--------------|-------------|-----------------------------------------|
| `--work-dir` | (Pflicht)   | Datenpfad für SQLite-DB und Laufzeitdaten |
| `--port`     | `5001`      | HTTP-Port                               |
| `--host`     | `0.0.0.0`   | Bind-Adresse                            |
| `--reload`   | –           | Auto-Reload bei Dateiänderungen         |

Die Web-Oberfläche ist danach erreichbar unter: `http://localhost:9999`

## Projektstruktur

```
backupctl/
├── _cli.py            # Einstiegspunkt (CLI)
├── _app.py            # ASGI-App-Factory
├── _paths.py          # Pfad-Utilities
├── runner.py          # Job-Executor (Borg, Rsync, Proxmox)
├── api/               # FastAPI-Router und SQLite-Backend
└── modules/           # Feature-Module
    ├── borg/
    ├── rsync/
    ├── proxmox_lxc/
    ├── proxmox_hosts/
    ├── proxmox_jobs/
    └── remotes/
```
