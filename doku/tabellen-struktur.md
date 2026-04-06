# Tabellen-Struktur – astrapi-backup

Stand: 2026-04-06  
CSS: `table-layout: fixed` — explizite Breiten sind garantiert, flexible Spalten teilen den Rest.  
Kein horizontaler Scroll (`overflow-x: hidden`), die rechten Festspalten sind immer sichtbar.

---

## Kern-Struktur (alle Module)

| Klasse         | Min-Breite | Max-Breite | Verhalten                        |
|----------------|------------|------------|----------------------------------|
| `col-name`     | 250px      | 250px      | truncate + fett (core: Name)     |
| *(modul-spez.)* | —         | flex       | je nach Modul                    |
| `col-type`     | 60px       | 60px       | Typ-Badge (optional)             |
| `col-last-run` | 150px      | 150px      | kein Wrap, truncate (opt.)       |
| `col-status`   | 60px       | 60px       | Status-Badge (immer)             |
| `col-actions`  | 60px       | 60px       | ⋮-Menü (immer)                  |

`col-last-run` wird über `has_run_buttons` gesteuert (default `True`).

---

## Borg

| # | Spalte       | Klasse         | Min   | Max   | Inhalt                   |
|---|--------------|----------------|-------|-------|--------------------------|
| 1 | Name         | `col-name`     | 250px | 250px | Item-ID                  |
| 2 | Quelle       | `col-trunc`    | —     | flex  | Remote-Host + Pfad       |
| 3 | Ziel         | `col-trunc`    | —     | flex  | Remote-Host + Pfad       |
| 4 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`               |
| 5 | Status       | `col-status`   | 60px  | 60px  | Status-Badge             |
| 6 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü                 |

---

## Rsync

| # | Spalte       | Klasse         | Min   | Max   | Inhalt       |
|---|--------------|----------------|-------|-------|--------------|
| 1 | Name         | `col-name`     | 250px | 250px | Item-ID      |
| 2 | Quelle       | `col-trunc`    | —     | flex  | Quellpfad    |
| 3 | Ziel         | `col-trunc`    | —     | flex  | Zielpfad     |
| 4 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`   |
| 5 | Status       | `col-status`   | 60px  | 60px  | Status-Badge |
| 6 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü     |

---

## Proxmox Hosts

| # | Spalte       | Klasse         | Min   | Max   | Inhalt                          |
|---|--------------|----------------|-------|-------|---------------------------------|
| 1 | Name         | `col-name`     | 250px | 250px | `description` (= Hostname/IP)   |
| 2 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`                      |
| 3 | Status       | `col-status`   | 60px  | 60px  | Status-Badge                    |
| 4 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü                        |

---

## Proxmox Jobs

| # | Spalte       | Klasse         | Min   | Max   | Inhalt                              |
|---|--------------|----------------|-------|-------|-------------------------------------|
| 1 | Name         | `col-name`     | 250px | 250px | Item-ID                             |
| 2 | Typ          | `col-type`     | 60px  | 60px  | vzdump / custom *(TODO: als Badge)* |
| 3 | Host         | `col-trunc`    | —     | flex  | Hostname/IP                         |
| 4 | Job          | `col-trunc`    | —     | flex  | Job-Name                            |
| 5 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`                          |
| 6 | Status       | `col-status`   | 60px  | 60px  | Status-Badge                        |
| 7 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü                            |

---

## Proxmox LXC

| # | Spalte       | Klasse         | Min   | Max   | Inhalt       |
|---|--------------|----------------|-------|-------|--------------|
| 1 | Name         | `col-name`     | 250px | 250px | Item-ID      |
| 2 | CT-ID        | `col-type`     | 60px  | 60px  | vmid         |
| 3 | Node         | `col-trunc`    | —     | flex  | Node-Name    |
| 4 | Letzter Lauf | `col-last-run` | 150px | 150px | `last_run`   |
| 5 | Status       | `col-status`   | 60px  | 60px  | Status-Badge |
| 6 | ⋮            | `col-actions`  | 60px  | 60px  | Ctx-Menü     |

---

## Remotes

`has_run_buttons=False` → kein col-last-run.

| # | Spalte       | Klasse        | Min  | Max  | Inhalt                    |
|---|--------------|---------------|------|------|---------------------------|
| 1 | Name         | `col-name`    | —    | flex | Item-ID                   |
| 2 | SSH-Benutzer | `col-trunc`   | —    | flex | user@host                 |
| 3 | MAC          | `col-trunc`   | —    | flex | MAC-Adresse               |
| 4 | Status       | `col-status`  | 60px | 60px | Host on/off               |
| 5 | ⋮            | `col-actions` | 60px | 60px | Ctx-Menü                  |

---

## CSS-Regeln (Core — `app.css`)

```css
/* Feste Spalten */
.ds-list-table .col-type     { width:  60px; min-width:  60px; }
.ds-list-table .col-last-run { width: 150px; min-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ds-list-table .col-status   { width:  60px; min-width:  60px; }
.ds-list-table .col-actions  { width:  60px; min-width:  60px; }

/* col-name: 250px im Core-Header (inline style), flex für modul-eigene Spalten */
.ds-list-table .col-name     { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-list-table .col-trunc    { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Kein horizontaler Scroll */
.ds-list-table-wrap-scroll   { overflow-x: hidden; }
.ds-list-table               { width: 100%; table-layout: fixed; }
```
