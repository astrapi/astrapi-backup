# backupctl – Kontext für Claude Code

## Architektur

Dreischichtige Struktur:
- `core/system/` — Basis: DB, Logger, Secrets, Reachability, Cmd, Format
- `core/modules/` — generische Module (scheduler, notify, activity_log, settings, sysinfo, remotes)
- `app/modules/` — app-spezifische Module (borg, rsync, proxmox_*)
- `app/overrides/` — überschreibt/erweitert Core-Module als flache `.py`-Dateien
- `core/ui/` — FastAPI/Jinja2-Infrastruktur (module_registry, settings_registry, crud_router, htmx_crud_router)

## Bereits umgesetzte Refactorings

### Generische CRUD-Infrastruktur
- `core/ui/htmx_crud_router.py` — `make_htmx_crud_router(key, schema_path, *, post_process=None)` generiert HTMX-Form-basierte CRUD-Routen (create, edit, delete, toggle); alle 5 `app/modules/*/api.py` nutzen es

### Logger
- `core/system/logger.py` — `log_context` Contextmanager; alle 5 `app/modules/*/jobs.py` nutzen `with log_context(...):`

### Borg
- `app/modules/borg/utils.py` — `borg_bin()`, `borg_env()`
- `app/modules/borg/storage.py` — Borg-Cache-Tabellen (SQLite)

### Utilities
- `core/system/format.py` — `fmt_bytes()`
- `core/modules/scheduler/job_runner.py` — `run_all()`, `run_logged()`

### Registry
- `core/ui/module_registry.py` — lädt auch flache `.py`-Dateien (nicht nur Pakete)
- `app/overrides/sysinfo.py` — flache Override-Datei (kein `__init__.py` mehr nötig)

## Offene Verbesserungen (nächste Schritte)

### Einfach (hoher Nutzen, geringer Aufwand)

1. **Flexible ID-Suche als Helper** — dieses Muster steht in `preview()` und `run_single()` aller 5 `jobs.py`:
   ```python
   config.get(item_id) or config.get(int(item_id) if str(item_id).isdigit() else item_id)
   ```
   → `get_entry(config, item_id)` in `api/storage.py` oder `core/system/db.py`

2. **`preview_item()` Endpunkt generisch machen** — in allen 5 `api.py` identisch (nur Jobs-Modul verschieden); als Parameter in `make_htmx_crud_router` aufnehmen

### Mittel (mehr Aufwand)

3. **Singleton + Shim-Muster vereinheitlichen** — Scheduler, NotifyEngine, SettingsRegistry, ModuleRegistry haben alle: private Instanz + viele Shim-Funktionen à `return _instance.method(args)`
