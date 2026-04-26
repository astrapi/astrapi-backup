# astrapi-backup

Web-UI zur zentralen Verwaltung von Backup-Jobs (Borg, Rsync, Proxmox, Remote-Geräte).
Aufgebaut auf **astrapi-core** (FastAPI + HTMX + Jinja2).

## Stack

| Komponente | Details |
|---|---|
| Framework | astrapi-core (FastAPI + HTMX) |
| Persistenz | SQLite |
| Verschlüsselung | Fernet (Secrets via astrapi-core) |
| Python | ≥ 3.11 |

## Voraussetzungen

### Systemabhängigkeiten

```bash
apt install borgbackup wakeonlan openssh-client
```

> Borg wird unter `/var/lib/backupadm/.venv/bin/borg` erwartet.

## Setup (Entwicklung)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ../astrapi-core   # Schwesterprojekt
pip install -e .
```

## Starten

```bash
astrapi-backup --work-dir data --port 5001
```

**Mit Auto-Reload (Entwicklung):**

```bash
astrapi-backup --work-dir data --port 5001 --reload
```

| Parameter | Standard | Beschreibung |
|---|---|---|
| `--work-dir` | (Pflicht) | Datenpfad für SQLite-DB und Laufzeitdaten |
| `--port` | `5001` | HTTP-Port |
| `--host` | `0.0.0.0` | Bind-Adresse |
| `--reload` | – | Auto-Reload bei Dateiänderungen |

Die Web-Oberfläche ist danach erreichbar unter: `http://localhost:5001`

## Projektstruktur

```
astrapi_backup/
├── _cli.py            # Einstiegspunkt (CLI)
├── _app.py            # ASGI-App-Factory
├── _paths.py          # Pfad-Utilities
├── runner.py          # Job-Dispatcher
├── api/               # FastAPI-Router und SQLite-Backend
└── modules/           # Feature-Module
    ├── borg/          # Borg-Backup
    ├── rsync/         # Rsync
    ├── proxmox_lxc/   # Proxmox LXC-Container
    ├── proxmox_hosts/ # Proxmox-Host-Backups
    ├── proxmox_jobs/  # Proxmox-Job-Verwaltung
    └── remotes/       # Remote-Geräte (WoL, SSH)
```

## Tests

```bash
pytest tests/unit/
```
