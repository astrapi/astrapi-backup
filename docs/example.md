# UI-Komponenten-Architektur – Modul Borg

Template-Hierarchie, CSS-Klassen und HTMX-Interaktionsmuster spezifisch für das Borg-Backup-Modul.

---

## 1 · Modulstruktur im Überblick

```mermaid
flowchart TD
    core["astrapi-core<br/>content.html + list_wrapper_inner.html"]
    borg["<b>borg/</b>"]

    core -->|"GET /ui/borg/content"| borg

    borg --> ui["ui.py<br/>make_crud_router()<br/>Filter: source · target · status"]
    borg --> api["api.py<br/>make_htmx_crud_router()<br/>+ archives · stats · browse · preview"]
    borg --> jobs["jobs.py<br/>run_single(item_id)<br/>preview(item_id)"]
    borg --> storage["storage.py<br/>SqliteTableStore('borg')<br/>+ Archive-/File-/Stats-Cache"]
```

---

## 2 · Vollständige Template-Hierarchie

```mermaid
flowchart TD
    lwi["<b>list_wrapper_inner.html</b> (Core)<br/><code>.content-items</code> / <code>.content-list</code><br/>Alpine: viewToggle('borg')"]

    lwi --> card["<code>&lt;article class=ds-card on|off&gt;</code><br/>pro Borg-Job"]

    card --> ch["<code>.card-header</code><br/>description · toggle_switch"]
    card --> cb["<code>.card-body</code><br/>{% include content_template %}"]
    card --> cf["<code>.card-footer</code>"]

    cb --> cardbody["<b>borg/partials/card_body.html</b><br/><code>.meta-grid</code><br/>Quelle: [remote:]pfad<br/>Ziel: [remote:]pfad"]

    cf --> actions["<b>ui_macros.html</b> Card-Actions"]
    actions --> run["run_button<br/>POST /api/borg/{id}/run"]
    actions --> log["log_button<br/>GET /api/borg/{id}/logs"]
    actions --> arc["archives_button<br/>GET /ui/borg/{id}/archives"]
    actions --> stats["stats_button<br/>GET /ui/borg/{id}/stats"]
    actions --> prev["preview_button<br/>GET /ui/borg/{id}/preview"]

    lwi --> listview["<b>Tabellen-Ansicht</b><br/><code>.content-list</code>"]
    listview --> lh["<b>borg/partials/list_header.html</b><br/>Name · Quelle · Ziel · Letzter Run · Status"]
    listview --> lr["<b>borg/partials/list_row.html</b><br/>Zeilen-Spalten (gleiche Felder)"]
```

---

## 3 · Filter-Leiste (content-header)

```mermaid
flowchart LR
    header["<code>.content-header-actions</code>"]
    header --> f1["<select> Quelle<br/>GET /api/remotes/for-select?type=borg_source"]
    header --> f2["<select> Ziel<br/>GET /api/remotes/for-select?type=borg_target&local=0"]
    header --> f3["<select> Status<br/>neu · ok · error"]
    header --> add["<b>add_button</b><br/>GET /ui/borg/create"]
```

---

## 4 · Modal-Dialoge

```mermaid
flowchart TD
    body["<code>&lt;body&gt;</code><br/>hx-swap='beforeend'"]

    body --> cem["<b>create_edit_modal.html</b> (Core)<br/><code>#create-edit-modal</code><br/>schema.yaml: description · enabled<br/>Quelle: source_remote_id · source_path<br/>Ziel: target_remote_id · target_path<br/>Skripte & Filter<br/>POST /api/borg/ · PUT /api/borg/{id}"]

    body --> lm["<b>log_modal.html</b> (Core)<br/><code>#log-modal</code><br/>Statisch: GET /api/borg/{id}/logs<br/>Live-SSE: GET /api/borg/{id}/logs/stream"]

    body --> amod["<b>borg/modals/archives.html</b><br/><code>#borg-archive-modal</code><br/><code>#borg-archive-content</code> (HTMX-Ziel)<br/>max-width: 920px"]

    body --> smod["<b>borg/modals/stats.html</b><br/><code>#borg-stats-modal</code><br/><code>#borg-stats-content</code> (HTMX-Ziel)<br/>max-width: 680px"]

    body --> prev["<b>preview_modal.html</b> (Core)<br/><code>#preview-modal</code><br/>GET /api/borg/{id}/preview"]

    body --> conf["<b>confirm_modal.html</b> (Core)<br/>Löschen-Bestätigung"]

    amod --> alist["<b>borg/partials/archives_list.html</b><br/>Liste der Archive<br/>Klick → hx-get=…/browse"]
    amod --> browse["<b>borg/partials/browse.html</b><br/>Verzeichnis-Browser<br/>Breadcrumbs · dirs · files<br/>Download: GET /api/borg/{id}/archives/{name}/download-bundle"]

    smod --> scont["<b>borg/partials/stats_content.html</b><br/>Repo-Statistiken (Größe, Deduplizierung)"]
```

---

## 5 · HTMX-Datenfluss Borg

```mermaid
sequenceDiagram
    participant B as Browser
    participant UI as /ui/borg/
    participant API as /api/borg/

    B->>UI: GET /ui/borg/content
    UI-->>B: content.html (innerHTML #main-content)

    B->>UI: GET /ui/borg/create
    UI-->>B: create_edit_modal.html (beforeend body)

    B->>API: POST /api/borg/
    API-->>B: 200 – Reload
    B->>UI: GET /ui/borg/content
    UI-->>B: Aktualisierte Jobliste

    B->>API: POST /api/borg/{id}/run
    API-->>B: 202 Accepted

    loop Polling alle 2,5s (status-inline--running)
        B->>UI: GET /ui/borg/status
        UI-->>B: list_wrapper_inner (innerHTML #mod-borg)
    end

    B->>API: GET /api/borg/{id}/logs/stream
    API-->>B: SSE-Events (Logzeilen)
    Note over B,API: EventSource – schließt bei 'done'-Event

    B->>UI: GET /ui/borg/{id}/archives
    UI-->>B: archives.html (beforeend body)

    B->>API: GET /api/borg/{id}/archives/list
    API-->>B: archives_list.html (innerHTML #borg-archive-content)

    B->>API: GET /api/borg/{id}/archives/{name}/browse?path=…
    API-->>B: browse.html (innerHTML #borg-archive-content)

    B->>UI: GET /ui/borg/{id}/stats
    UI-->>B: stats.html (beforeend body)

    B->>API: POST /api/borg/{id}/stats/refresh
    API-->>B: stats_content.html (innerHTML #borg-stats-content)
```

---

## 6 · API-Endpunkte (Borg)

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/ui/borg/content` | Vollständige Jobliste (content.html) |
| `GET` | `/ui/borg/status` | Polling-Schnappschuss (laufende Jobs) |
| `GET` | `/ui/borg/create` | Create-Modal |
| `GET` | `/ui/borg/{id}/edit` | Edit-Modal |
| `GET` | `/ui/borg/{id}/archives` | Archives-Modal |
| `GET` | `/ui/borg/{id}/stats` | Stats-Modal |
| `GET` | `/ui/borg/{id}/preview` | Preview-Modal |
| `POST` | `/api/borg/` | Job anlegen |
| `PUT` | `/api/borg/{id}` | Job bearbeiten |
| `DELETE` | `/api/borg/{id}` | Job löschen |
| `POST` | `/api/borg/{id}/run` | Backup starten |
| `GET` | `/api/borg/{id}/logs` | Log (statisch, optional `?date=`) |
| `GET` | `/api/borg/{id}/logs/stream` | Log-SSE-Stream |
| `GET` | `/api/borg/{id}/archives/list` | Archivliste (cached) |
| `POST` | `/api/borg/{id}/archives/refresh` | Archivliste neu laden |
| `GET` | `/api/borg/{id}/archives/{name}/browse` | Verzeichnis-Browser |
| `GET` | `/api/borg/{id}/archives/{name}/download-bundle` | TAR-Download |
| `GET` | `/api/borg/{id}/stats` | Stats (cached) |
| `POST` | `/api/borg/{id}/stats/refresh` | Stats neu laden |
| `GET` | `/api/borg/{id}/preview` | Vorschau (dry-run) |

---

## 7 · Cache-Schichten (storage.py)

```mermaid
flowchart LR
    sqlite["SQLite<br/>(astrapi-core)"]
    sqlite --> ac["Archive-Cache<br/>get_archive_cache()<br/>save_archive_list_cache()"]
    sqlite --> fc["File-Cache<br/>get_file_cache()<br/>save_file_cache_for_archive()"]
    sqlite --> sc["Stats-Cache<br/>get_stats_cache()<br/>save_stats_cache()"]
    sqlite --> main["Haupt-Tabelle borg<br/>SqliteTableStore('borg')"]
```
