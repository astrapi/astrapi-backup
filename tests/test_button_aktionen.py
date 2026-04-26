"""tests/test_button_aktionen.py

Prüft ob alle Button-Aktionen (Speichern, Bearbeiten, Toggle, Löschen,
Job starten, Wake) die erwarteten HTTP-Statuscodes liefern und die
erwarteten Datenbankänderungen bewirken.

Jeder Test erstellt einen isolierten Testeintrag und räumt ihn am Ende
auf (try/finally). Alle Testeinträge tragen '__test__' im Beschreibungsfeld.
"""

import sqlite3

# ── DB-Hilfsfunktionen ────────────────────────────────────────────────────────


def _next_id(work_dir, table: str) -> int:
    """Gibt die ID zurück, die SQLite beim nächsten AUTOINCREMENT-INSERT vergibt."""
    con = sqlite3.connect(str(work_dir / "data" / "app.db"))
    try:
        row = con.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
        return (row[0] + 1) if row else 1
    except sqlite3.OperationalError:
        return 1
    finally:
        con.close()


def _item_exists(work_dir, table: str, item_id: int) -> bool:
    """Prüft ob ein Eintrag in der DB vorhanden ist."""
    con = sqlite3.connect(str(work_dir / "data" / "app.db"))
    try:
        row = con.execute(f"SELECT id FROM {table} WHERE id=?", (item_id,)).fetchone()
        return row is not None
    finally:
        con.close()


def _get_field(work_dir, table: str, item_id: int, field: str):
    """Liest ein einzelnes Feld direkt aus der DB."""
    con = sqlite3.connect(str(work_dir / "data" / "app.db"))
    try:
        row = con.execute(f"SELECT {field} FROM {table} WHERE id=?", (item_id,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


# ── Remotes ───────────────────────────────────────────────────────────────────

_R = {
    "host": "__test__",
    "ssh_user": "backupadm",
    "ssh_port": "22",
    "enabled": "on",
}


def test_remotes_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen Remote an."""
    new_id = _next_id(work_dir, "remotes")
    try:
        resp = client.post("/api/remotes/create", data=_R)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "remotes", new_id)
    finally:
        client.delete(f"/api/remotes/{new_id}/delete")


def test_remotes_bearbeiten(client, work_dir):
    """Speichern-Button im Bearbeiten-Dialog aktualisiert den Remote."""
    new_id = _next_id(work_dir, "remotes")
    client.post("/api/remotes/create", data=_R)
    try:
        resp = client.patch(
            f"/api/remotes/{new_id}/edit",
            data={**_R, "host": "__test_edited__"},
        )
        assert resp.status_code == 200
        assert resp.json()["host"] == "__test_edited__"
    finally:
        client.delete(f"/api/remotes/{new_id}/delete")


def test_remotes_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten Remote auf aktiv."""
    new_id = _next_id(work_dir, "remotes")
    client.post("/api/remotes/create", data={**_R, "enabled": ""})
    try:
        resp = client.post(f"/api/remotes/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/remotes/{new_id}/delete")


def test_remotes_loeschen(client, work_dir):
    """Löschen-Button (nach Bestätigung) entfernt den Remote aus der DB."""
    new_id = _next_id(work_dir, "remotes")
    client.post("/api/remotes/create", data=_R)
    resp = client.delete(f"/api/remotes/{new_id}/delete")
    assert resp.status_code < 300
    assert not _item_exists(work_dir, "remotes", new_id)


def test_remotes_wake_ohne_mac(client, work_dir):
    """Wake-Button ohne konfigurierte MAC-Adresse liefert 400."""
    new_id = _next_id(work_dir, "remotes")
    client.post("/api/remotes/create", data=_R)
    try:
        resp = client.post(f"/api/remotes/{new_id}/wake")
        assert resp.status_code == 400
    finally:
        client.delete(f"/api/remotes/{new_id}/delete")


# ── Borg ──────────────────────────────────────────────────────────────────────

_B = {
    "description": "__test__",
    "source_path": "/tmp/test_src",
    "target_path": "/tmp/test_tgt",
    "enabled": "on",
}


def test_borg_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen Borg-Job an."""
    new_id = _next_id(work_dir, "borg")
    try:
        resp = client.post("/api/borg/create", data=_B)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "borg", new_id)
    finally:
        client.delete(f"/api/borg/{new_id}/delete")


def test_borg_bearbeiten(client, work_dir):
    """Speichern-Button im Bearbeiten-Dialog aktualisiert den Borg-Job."""
    new_id = _next_id(work_dir, "borg")
    client.post("/api/borg/create", data=_B)
    try:
        resp = client.patch(
            f"/api/borg/{new_id}/edit",
            data={**_B, "description": "__test_edited__"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "__test_edited__"
    finally:
        client.delete(f"/api/borg/{new_id}/delete")


def test_borg_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten Borg-Job auf aktiv."""
    new_id = _next_id(work_dir, "borg")
    client.post("/api/borg/create", data={**_B, "enabled": ""})
    try:
        resp = client.post(f"/api/borg/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/borg/{new_id}/delete")


def test_borg_loeschen(client, work_dir):
    """Löschen-Button entfernt den Borg-Job aus der DB."""
    new_id = _next_id(work_dir, "borg")
    client.post("/api/borg/create", data=_B)
    resp = client.delete(f"/api/borg/{new_id}/delete")
    assert resp.status_code in (200, 204)
    assert not _item_exists(work_dir, "borg", new_id)


def test_borg_ausfuehren(client, work_dir):
    """Ausführen-Button startet den Borg-Job (Hintergrundthread, 200 sofort)."""
    new_id = _next_id(work_dir, "borg")
    client.post("/api/borg/create", data=_B)
    try:
        resp = client.post(f"/api/borg/{new_id}/run")
        assert resp.status_code == 200
    finally:
        client.delete(f"/api/borg/{new_id}/delete")


# ── Rsync ─────────────────────────────────────────────────────────────────────

_RS = {
    "description": "__test__",
    "type": "intern",
    "source_path": "/tmp/test_src",
    "target_path": "/tmp/test_tgt",
    "enabled": "on",
}


def test_rsync_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen Rsync-Job an."""
    new_id = _next_id(work_dir, "rsync")
    try:
        resp = client.post("/api/rsync/create", data=_RS)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "rsync", new_id)
    finally:
        client.delete(f"/api/rsync/{new_id}/delete")


def test_rsync_bearbeiten(client, work_dir):
    """Speichern-Button im Bearbeiten-Dialog aktualisiert den Rsync-Job."""
    new_id = _next_id(work_dir, "rsync")
    client.post("/api/rsync/create", data=_RS)
    try:
        resp = client.patch(
            f"/api/rsync/{new_id}/edit",
            data={**_RS, "description": "__test_edited__"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "__test_edited__"
    finally:
        client.delete(f"/api/rsync/{new_id}/delete")


def test_rsync_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten Rsync-Job auf aktiv."""
    new_id = _next_id(work_dir, "rsync")
    client.post("/api/rsync/create", data={**_RS, "enabled": ""})
    try:
        resp = client.post(f"/api/rsync/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/rsync/{new_id}/delete")


def test_rsync_loeschen(client, work_dir):
    """Löschen-Button entfernt den Rsync-Job aus der DB."""
    new_id = _next_id(work_dir, "rsync")
    client.post("/api/rsync/create", data=_RS)
    resp = client.delete(f"/api/rsync/{new_id}/delete")
    assert resp.status_code in (200, 204)
    assert not _item_exists(work_dir, "rsync", new_id)


def test_rsync_ausfuehren(client, work_dir):
    """Ausführen-Button startet den Rsync-Job (Hintergrundthread, 200 sofort)."""
    new_id = _next_id(work_dir, "rsync")
    client.post("/api/rsync/create", data=_RS)
    try:
        resp = client.post(f"/api/rsync/{new_id}/run")
        assert resp.status_code == 200
    finally:
        client.delete(f"/api/rsync/{new_id}/delete")


# ── Proxmox LXC ───────────────────────────────────────────────────────────────

_LXC = {
    "vmid": "99999",  # NOT NULL in DB – muss mitgeschickt werden
    "description": "__test__",
    "enabled": "on",
}


def test_proxmox_lxc_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen LXC-Eintrag an."""
    new_id = _next_id(work_dir, "proxmox_lxc")
    try:
        resp = client.post("/api/proxmox_lxc/create", data=_LXC)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "proxmox_lxc", new_id)
    finally:
        client.delete(f"/api/proxmox_lxc/{new_id}/delete")


def test_proxmox_lxc_bearbeiten(client, work_dir):
    """Speichern-Button im Bearbeiten-Dialog aktualisiert den LXC-Eintrag."""
    new_id = _next_id(work_dir, "proxmox_lxc")
    client.post("/api/proxmox_lxc/create", data=_LXC)
    try:
        resp = client.patch(
            f"/api/proxmox_lxc/{new_id}/edit",
            data={**_LXC, "description": "__test_edited__"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "__test_edited__"
    finally:
        client.delete(f"/api/proxmox_lxc/{new_id}/delete")


def test_proxmox_lxc_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten LXC-Eintrag auf aktiv."""
    new_id = _next_id(work_dir, "proxmox_lxc")
    client.post("/api/proxmox_lxc/create", data={**_LXC, "enabled": ""})
    try:
        resp = client.post(f"/api/proxmox_lxc/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/proxmox_lxc/{new_id}/delete")


def test_proxmox_lxc_loeschen(client, work_dir):
    """Löschen-Button entfernt den LXC-Eintrag aus der DB."""
    new_id = _next_id(work_dir, "proxmox_lxc")
    client.post("/api/proxmox_lxc/create", data=_LXC)
    resp = client.delete(f"/api/proxmox_lxc/{new_id}/delete")
    assert resp.status_code in (200, 204)
    assert not _item_exists(work_dir, "proxmox_lxc", new_id)


def test_proxmox_lxc_ausfuehren(client, work_dir):
    """Ausführen-Button startet den LXC-Backup (Hintergrundthread, 200 sofort)."""
    new_id = _next_id(work_dir, "proxmox_lxc")
    client.post("/api/proxmox_lxc/create", data=_LXC)
    try:
        resp = client.post(f"/api/proxmox_lxc/{new_id}/run")
        assert resp.status_code == 200
    finally:
        client.delete(f"/api/proxmox_lxc/{new_id}/delete")


# ── Proxmox Hosts ─────────────────────────────────────────────────────────────

_PH = {
    "description": "__test__",
    "enabled": "on",
}


def test_proxmox_hosts_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen Host-Eintrag an."""
    new_id = _next_id(work_dir, "proxmox_hosts")
    try:
        resp = client.post("/api/proxmox_hosts/create", data=_PH)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "proxmox_hosts", new_id)
    finally:
        client.delete(f"/api/proxmox_hosts/{new_id}/delete")


def test_proxmox_hosts_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten Host-Eintrag auf aktiv."""
    new_id = _next_id(work_dir, "proxmox_hosts")
    client.post("/api/proxmox_hosts/create", data={**_PH, "enabled": ""})
    try:
        resp = client.post(f"/api/proxmox_hosts/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/proxmox_hosts/{new_id}/delete")


def test_proxmox_hosts_loeschen(client, work_dir):
    """Löschen-Button entfernt den Host-Eintrag aus der DB."""
    new_id = _next_id(work_dir, "proxmox_hosts")
    client.post("/api/proxmox_hosts/create", data=_PH)
    resp = client.delete(f"/api/proxmox_hosts/{new_id}/delete")
    assert resp.status_code in (200, 204)
    assert not _item_exists(work_dir, "proxmox_hosts", new_id)


def test_proxmox_hosts_ausfuehren(client, work_dir):
    """Ausführen-Button startet den Host-Backup (Hintergrundthread, 200 sofort)."""
    new_id = _next_id(work_dir, "proxmox_hosts")
    client.post("/api/proxmox_hosts/create", data=_PH)
    try:
        resp = client.post(f"/api/proxmox_hosts/{new_id}/run")
        assert resp.status_code == 200
    finally:
        client.delete(f"/api/proxmox_hosts/{new_id}/delete")


# ── Proxmox Jobs ──────────────────────────────────────────────────────────────

_PJ = {
    "type": "pbs",  # kein description-Feld in proxmox_jobs
    "enabled": "on",
}


def test_proxmox_jobs_erstellen(client, work_dir):
    """Speichern-Button im Erstellen-Dialog legt neuen Job-Eintrag an."""
    new_id = _next_id(work_dir, "proxmox_jobs")
    try:
        resp = client.post("/api/proxmox_jobs/create", data=_PJ)
        assert resp.status_code == 200
        assert _item_exists(work_dir, "proxmox_jobs", new_id)
    finally:
        client.delete(f"/api/proxmox_jobs/{new_id}/delete")


def test_proxmox_jobs_toggle(client, work_dir):
    """Toggle-Button schaltet einen deaktivierten Job-Eintrag auf aktiv."""
    new_id = _next_id(work_dir, "proxmox_jobs")
    client.post("/api/proxmox_jobs/create", data={**_PJ, "enabled": ""})
    try:
        resp = client.post(f"/api/proxmox_jobs/{new_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
    finally:
        client.delete(f"/api/proxmox_jobs/{new_id}/delete")


def test_proxmox_jobs_loeschen(client, work_dir):
    """Löschen-Button entfernt den Job-Eintrag aus der DB."""
    new_id = _next_id(work_dir, "proxmox_jobs")
    client.post("/api/proxmox_jobs/create", data=_PJ)
    resp = client.delete(f"/api/proxmox_jobs/{new_id}/delete")
    assert resp.status_code in (200, 204)
    assert not _item_exists(work_dir, "proxmox_jobs", new_id)


def test_proxmox_jobs_ausfuehren(client, work_dir):
    """Ausführen-Button startet den PBS-Job (Hintergrundthread, 200 sofort)."""
    new_id = _next_id(work_dir, "proxmox_jobs")
    client.post("/api/proxmox_jobs/create", data=_PJ)
    try:
        resp = client.post(f"/api/proxmox_jobs/{new_id}/run")
        assert resp.status_code == 200
    finally:
        client.delete(f"/api/proxmox_jobs/{new_id}/delete")
