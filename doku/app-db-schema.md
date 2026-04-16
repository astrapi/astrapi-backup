# Datenbankschema – app.db

Stand: 2026-04-16  
Datei: `<work-dir>/app.db` (SQLite, WAL-Modus)  
Quelle der Wahrheit: `astrapi_backup/api/storage.py`, `astrapi_backup/modules/remotes/__init__.py`,
`astrapi-core/astrapi/core/system/db.py`, `activity_log.py`, `modules/borg/storage.py`

---

## Übersicht

| Tabelle                | Herkunft      | Zweck                                    |
|------------------------|---------------|------------------------------------------|
| `settings`             | core          | Globaler Key-Value-Konfigurationsspeicher |
| `kvstore`              | core          | Generischer Collection-Key-Value-Speicher |
| `activity_log`         | core          | Job-Läufe und Ereignisse aller Module    |
| `activity_log_lines`   | core          | Einzelne Log-Zeilen je Lauf              |
| `borg`                 | astrapi-backup | Borg-Backup-Jobs                        |
| `rsync`                | astrapi-backup | Rsync-Jobs                              |
| `proxmox_lxc`          | astrapi-backup | Proxmox-LXC-Container-Backup-Jobs       |
| `proxmox_hosts`        | astrapi-backup | Proxmox-Host-Backup-Jobs                |
| `proxmox_jobs`         | astrapi-backup | Proxmox-Backup-Jobs (PBS-Jobs)          |
| `remotes`              | astrapi-backup | Remote-Geräte (WoL, SSH, API)           |
| `borg_archive_cache`   | astrapi-backup | Cache der Borg-Archivlisten             |
| `borg_file_cache`      | astrapi-backup | Cache der Dateieinträge je Archiv       |
| `borg_stats_cache`     | astrapi-backup | Cache der Borg-Repo-Statistiken         |

> **Listenfelder:** Mehrwertige Felder (`pre_hooks`, `post_hooks`, `exclude`, `extra_sources`,
> `types`) werden als `\n`-getrennter TEXT gespeichert und beim Lesen automatisch in Python-Listen
> umgewandelt. Im Formular werden sie als `list`- bzw. `multiselect`-Felder dargestellt.

---

## Core-Tabellen

### `settings`

Globaler Key-Value-Speicher für App-weite Einstellungen (z. B. `activity_log_migrated`).

| Spalte  | Typ  | Größe | Default | Zweck                        |
|---------|------|-------|---------|------------------------------|
| `key`   | TEXT | —     | —       | Eindeutiger Einstellungsname |
| `value` | TEXT | —     | `''`    | Einstellungswert als String  |

Primary Key: `key`

---

### `kvstore`

Generischer Speicher für Modul-Konfigurationen, die kein eigenes relationales Schema brauchen
(z. B. Settings-Registry, Scheduler-Konfigurationen). Werte sind JSON-codierte Strings.

| Spalte       | Typ  | Größe | Default | Zweck                                   |
|--------------|------|-------|---------|-----------------------------------------|
| `collection` | TEXT | —     | —       | Namensraum / Modul-Key (z. B. `notify`) |
| `key`        | TEXT | —     | —       | Schlüssel innerhalb der Collection      |
| `value`      | TEXT | —     | —       | Wert als JSON-String                    |

Primary Key: `(collection, key)`

---

### `activity_log`

Zentrales Log aller Job-Läufe und Ereignisse. Ersetzt die alte `job_history`-Tabelle.
Befüllt durch `history_start` / `history_finish` und direkt über `log_activity`.

| Spalte            | Typ     | Größe | Default | Zweck                                                         |
|-------------------|---------|-------|---------|---------------------------------------------------------------|
| `id`              | INTEGER | —     | auto    | Primärschlüssel                                               |
| `created_at`      | TEXT    | 19    | —       | Zeitstempel der Erstellung (`YYYY-MM-DD HH:MM:SS`)            |
| `started_at`      | TEXT    | 19    | —       | Startzeitpunkt des Jobs                                       |
| `finished_at`     | TEXT    | 19    | NULL    | Endzeitpunkt; NULL solange laufend                            |
| `log_type`        | TEXT    | —     | —       | Art des Eintrags: `job`, `event`, …                           |
| `module`          | TEXT    | —     | —       | Modul-Key: `borg`, `rsync`, `remotes`, …                     |
| `item_id`         | TEXT    | —     | NULL    | ID des betroffenen Items (Fremdschlüssel, nicht enforced)     |
| `description`     | TEXT    | —     | —       | Lesbare Beschreibung des Laufs / Ereignisses                  |
| `status`          | TEXT    | —     | —       | `running`, `ok`, `error`, `warning`, `info`                  |
| `severity`        | TEXT    | —     | NULL    | Optionale Schwere: `low`, `medium`, `high`                    |
| `mode`            | TEXT    | —     | NULL    | Ausführungsmodus: `run`, `debug`, …                           |
| `duration_s`      | INTEGER | —     | NULL    | Laufzeit in Sekunden                                          |
| `error_message`   | TEXT    | —     | NULL    | Fehlermeldung bei Status `error`                              |
| `error_code`      | TEXT    | —     | NULL    | Fehlercode (Exit-Code, HTTP-Status, …)                        |
| `error_traceback` | TEXT    | —     | NULL    | Python-Traceback als mehrzeiliger String                      |
| `bytes_processed` | INTEGER | —     | NULL    | Verarbeitete Bytes (Borg: Datenmenge)                         |
| `items_count`     | INTEGER | —     | NULL    | Anzahl verarbeiteter Elemente                                 |
| `changed_count`   | INTEGER | —     | NULL    | Anzahl geänderter Elemente                                    |
| `full_log`        | TEXT    | —     | NULL    | Vollständige stdout/stderr-Ausgabe                            |
| `metadata`        | TEXT    | —     | NULL    | Beliebige Zusatzdaten als JSON-Objekt                         |
| `parent_log_id`   | INTEGER | —     | NULL    | Referenz auf übergeordneten Lauf (Hierarchie)                 |
| `scheduler_job_id`| TEXT    | —     | NULL    | APScheduler-Job-ID des auslösenden Schedulers                 |
| `next_run`        | TEXT    | 19    | NULL    | Geplanter nächster Lauf-Zeitstempel                           |
| `archived_at`     | TEXT    | 19    | NULL    | Zeitstempel der Archivierung; NULL = aktiver Eintrag          |

Indizes: `log_type`, `module`, `status`, `created_at`, `item_id`

---

### `activity_log_lines`

Einzelne Log-Zeilen zu einem `activity_log`-Eintrag. Werden per SSE live gestreamt.

| Spalte   | Typ     | Größe | Default  | Zweck                                      |
|----------|---------|-------|----------|--------------------------------------------|
| `id`     | INTEGER | —     | auto     | Primärschlüssel; steigt monoton → SSE-Polling via `after_id` |
| `log_id` | INTEGER | —     | —        | Referenz auf `activity_log.id`             |
| `line`   | TEXT    | —     | —        | Eine Zeile Ausgabetext                     |
| `level`  | TEXT    | —     | `'INFO'` | Log-Level: `INFO`, `WARNING`, `ERROR`, …   |
| `ts`     | TEXT    | 8     | —        | Zeitstempel `HH:MM:SS`                     |

Index: `(log_id, id)` für effizientes SSE-Polling

---

## App-Tabellen (Job-Module)

### `borg`

Konfiguration der Borg-Backup-Jobs.

| Spalte            | Typ     | Größe | Default | Python-Key  | Zweck                                              |
|-------------------|---------|-------|---------|-------------|----------------------------------------------------|
| `id`              | INTEGER | —     | auto    | `id`        | Primärschlüssel                                    |
| `enabled`         | INTEGER | 1 bit | `1`     | `enabled`   | Job aktiv (1) oder deaktiviert (0)                 |
| `description`     | TEXT    | ≤50   | `''`    | `description` | Anzeigename des Jobs                             |
| `source_remote_id`| TEXT    | —     | NULL    | `source_remote_id` | FK auf `remotes.id` (Quell-Server)         |
| `source_path`     | TEXT    | ≤200  | `''`    | `source_path` | Quellverzeichnis auf dem Server                  |
| `target_remote_id`| TEXT    | —     | NULL    | `target_remote_id` | FK auf `remotes.id` (Ziel-Server)          |
| `target_path`     | TEXT    | ≤200  | `''`    | `target_path` | Borg-Repository-Pfad auf dem Ziel                |
| `pre_hooks`       | TEXT    | —     | NULL    | `pre`       | Pre-Script-Zeilen, `\n`-getrennt                   |
| `post_hooks`      | TEXT    | —     | NULL    | `post`      | Post-Script-Zeilen, `\n`-getrennt                  |
| `exclude`         | TEXT    | —     | NULL    | `exclude`   | Exclude-Pattern-Zeilen, `\n`-getrennt              |
| `last_run`        | TEXT    | 19    | NULL    | `last_run`  | Zeitstempel des letzten Laufs                      |
| `last_status`     | TEXT    | —     | NULL    | `last_status` | Status des letzten Laufs: `ok`, `error`, …       |

> `pre_hooks` / `post_hooks` / `exclude` werden beim Lesen als Listen zurückgegeben
> (`list_fields`). Python-Keys `pre` und `post` weichen von den DB-Spaltennamen ab (`col_in`/`col_out`-Mapping).
> Hostname und SSH-Zugangsdaten werden ausschließlich über `source_remote_id` / `target_remote_id`
> aus der `remotes`-Tabelle gelesen.

---

### `rsync`

Konfiguration der Rsync-Jobs.

| Spalte            | Typ     | Größe | Default | Zweck                                         |
|-------------------|---------|-------|---------|-----------------------------------------------|
| `id`              | INTEGER | —     | auto    | Primärschlüssel                               |
| `enabled`         | INTEGER | 1 bit | `1`     | Job aktiv (1) oder deaktiviert (0)            |
| `description`     | TEXT    | ≤50   | `''`    | Anzeigename des Jobs                          |
| `type`            | TEXT    | —     | `''`    | Job-Typ: `intern` oder `extern`               |
| `source_remote_id`| TEXT    | —     | NULL    | FK auf `remotes.id` (Quell-Server)            |
| `source_path`     | TEXT    | ≤200  | `''`    | Quellverzeichnis                              |
| `target_remote_id`| TEXT    | —     | NULL    | FK auf `remotes.id` (Ziel-Server)             |
| `target_path`     | TEXT    | ≤200  | `''`    | Zielverzeichnis                               |
| `last_run`        | TEXT    | 19    | NULL    | Zeitstempel des letzten Laufs                 |
| `last_status`     | TEXT    | —     | NULL    | Status des letzten Laufs                      |

> Hostname und SSH-Zugangsdaten werden ausschließlich über `source_remote_id` / `target_remote_id`
> aus der `remotes`-Tabelle gelesen.

---

### `proxmox_lxc`

Konfiguration der LXC-Container-Backups via Proxmox-API.

| Spalte      | Typ     | Größe | Default | Zweck                                          |
|-------------|---------|-------|---------|------------------------------------------------|
| `id`        | INTEGER | —     | auto    | Primärschlüssel                                |
| `vmid`      | INTEGER | —     | —       | Proxmox-Container-ID (CT-ID)                   |
| `description`| TEXT   | ≤100  | `''`    | Anzeigename                                    |
| `node`      | TEXT    | ≤100  | `''`    | Proxmox-Node-Name (wird zur Laufzeit aufgelöst)|
| `enabled`   | INTEGER | 1 bit | `1`     | Job aktiv                                      |
| `last_run`  | TEXT    | 19    | NULL    | Zeitstempel des letzten Laufs                  |
| `last_status`| TEXT   | —     | NULL    | Status des letzten Laufs                       |

---

### `proxmox_hosts`

Konfiguration der Proxmox-Host-Backups (vzdump / PBS-Sicherungen vom Host).

| Spalte         | Typ     | Größe | Default  | Python-Key    | Zweck                                               |
|----------------|---------|-------|----------|---------------|-----------------------------------------------------|
| `id`           | INTEGER | —     | auto  | `id`          | Primärschlüssel                                     |
| `description`  | TEXT    | ≤200  | `''`  | `description` | Hostname des Remotes (automatisch befüllt)          |
| `enabled`      | INTEGER | 1 bit | `1`   | `enabled`     | Job aktiv                                           |
| `remote_id`    | TEXT    | —     | NULL  | `remote_id`   | FK auf `remotes.id` (Proxmox Host)                  |
| `extra_sources`| TEXT    | —     | NULL  | `source`      | Zusätzliche Quellpfade, `\n`-getrennt               |
| `last_run`     | TEXT    | 19    | NULL  | `last_run`    | Zeitstempel des letzten Laufs                       |
| `last_status`  | TEXT    | —     | NULL  | `last_status` | Status des letzten Laufs                            |

> `extra_sources` wird als Liste gelesen. Python-Key `source` weicht vom DB-Spaltennamen ab.
> `namespace` (PBS-Namespace) ist hardcoded auf `host` in `jobs.py` und wird nicht in der DB gespeichert.

---

### `proxmox_jobs`

Proxmox-Backup-Server-Jobs (PBS-Jobs, die per API ausgelöst werden).

| Spalte      | Typ     | Größe | Default | Zweck                                      |
|-------------|---------|-------|---------|--------------------------------------------|
| `id`        | INTEGER | —     | auto    | Primärschlüssel                            |
| `job`       | TEXT    | ≤200  | `''`    | PBS-Job-ID oder Job-Name                   |
| `remote_id` | TEXT    | —     | NULL    | FK auf `remotes.id`                        |
| `type`      | TEXT    | ≤50   | `''`    | Job-Typ: `vzdump`, `sync`, …               |
| `enabled`   | INTEGER | 1 bit | `1`     | Job aktiv                                  |
| `last_run`  | TEXT    | 19    | NULL    | Zeitstempel des letzten Laufs              |
| `last_status`| TEXT   | —     | NULL    | Status des letzten Laufs                   |

---

## Remote-Geräte

### `remotes`

Konfiguration aller Remote-Geräte: SSH-Zugang, Wake-on-LAN, Proxmox-API-Token.

| Spalte            | Typ     | Größe | Default        | Zweck                                                             |
|-------------------|---------|-------|----------------|-------------------------------------------------------------------|
| `id`              | INTEGER | —     | auto           | Primärschlüssel                                                   |
| `host`            | TEXT    | ≤100  | `''`           | Hostname oder IP-Adresse                                          |
| `enabled`         | INTEGER | 1 bit | `1`            | Gerät aktiv                                                       |
| `mac`             | TEXT    | 17    | `''`           | MAC-Adresse für Wake-on-LAN (`aa:bb:cc:dd:ee:ff`)                 |
| `ssh_user`        | TEXT    | ≤50   | `'backupadm'`  | SSH-Benutzername für Backup-Verbindungen                          |
| `ssh_port`        | INTEGER | —     | `22`           | SSH-Port                                                          |
| `types`           | TEXT    | —     | `''`           | Verwendungsarten als `\n`-getrennte Liste: `borg`, `rsync`, `proxmox_node`, `proxmox_host`, `proxmox_backup` |
| `borg_bin`        | TEXT    | ≤200  | `''`           | Pfad zur Borg-Binary auf dem Remote-System                        |
| `api_token_id`    | TEXT    | ≤100  | `''`           | Proxmox-API-Token-ID (`user@realm!tokenname`)                     |
| `api_token_secret`| TEXT    | —     | `''`           | Proxmox-API-Token-Secret (Fernet-verschlüsselt)                   |
| `api_verify_ssl`  | INTEGER | 1 bit | `0`            | SSL-Zertifikat bei Proxmox-API verifizieren                       |
| `pbs_fingerprint` | TEXT    | —     | `''`           | PBS-Server-Fingerprint (TLS-Verifikation)                         |
| `pbs_datastore`   | TEXT    | —     | `''`           | PBS-Datastore-Name                                                |

> `types` wird beim Lesen als Python-Liste zurückgegeben (`list_fields=["types"]`).  
> `api_token_secret` wird über `get_secret_safe` ver-/entschlüsselt, nicht im Klartext gelesen.

---

## Borg-Cache-Tabellen

### `borg_archive_cache`

Liste aller bekannten Archive je Borg-Job. Wird nach jedem Backup und bei explizitem
Refresh aktualisiert.

| Spalte      | Typ     | Größe | Default | Zweck                                             |
|-------------|---------|-------|---------|---------------------------------------------------|
| `id`        | INTEGER | —     | auto    | Primärschlüssel                                   |
| `item_id`   | TEXT    | —     | —       | FK auf `borg.id` (als String)                     |
| `name`      | TEXT    | —     | —       | Archivname (z. B. `server-2026-04-13T02:00:01`)   |
| `time`      | TEXT    | 19    | —       | Erstellungszeitpunkt des Archivs (ISO 8601)       |
| `cached_at` | TEXT    | 19    | —       | Zeitstempel des letzten Cache-Updates             |

Index: `item_id`

---

### `borg_file_cache`

Dateibaum-Cache je Archiv. Befüllt nach Backup oder bei explizitem Browse-Request.
Ermöglicht das Durchsuchen von Archiven ohne erneuten Borg-Aufruf.

| Spalte    | Typ     | Größe | Default | Zweck                                             |
|-----------|---------|-------|---------|---------------------------------------------------|
| `id`      | INTEGER | —     | auto    | Primärschlüssel                                   |
| `item_id` | TEXT    | —     | —       | FK auf `borg.id`                                  |
| `archive` | TEXT    | —     | —       | Archivname (Referenz auf `borg_archive_cache.name`) |
| `path`    | TEXT    | —     | —       | Vollständiger Dateipfad im Archiv                 |
| `type`    | TEXT    | 1     | NULL    | Eintragstyp: `d` (Verzeichnis), `-` (Datei), …    |
| `size`    | INTEGER | —     | `0`     | Dateigröße in Bytes                               |
| `mtime`   | TEXT    | 19    | NULL    | Letzte Änderungszeit (ISO 8601)                   |
| `mode`    | TEXT    | 10    | NULL    | Unix-Berechtigungen (z. B. `drwxr-xr-x`)          |

Index: `(item_id, archive)` für schnellen Lookup beim Browse

---

### `borg_stats_cache`

Cache der `borg info --json`-Ausgabe je Repository. Enthält Größen, Deduplizierungsraten
und Archiv-Statistiken.

| Spalte       | Typ  | Größe | Default | Zweck                                         |
|--------------|------|-------|---------|-----------------------------------------------|
| `item_id`    | TEXT | —     | —       | PK; FK auf `borg.id`                          |
| `stats_json` | TEXT | —     | —       | Vollständige `borg info --json`-Ausgabe       |
| `cached_at`  | TEXT | 19    | —       | Zeitstempel des letzten Cache-Updates         |

Primary Key: `item_id` (ein Eintrag pro Job, wird per UPSERT aktualisiert)
