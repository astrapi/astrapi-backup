from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

# (Modul, Feld-Selector im Settings-Modal, Testwert)
# Nur Module mit settings.yaml (= die einen Einstellungen-Button haben).
# field_selector=None bei Modulen, die ausschließlich Checkboxen enthalten.
MODULES_WITH_SETTINGS = [
    ("borg",          "input[name='borg_bin']",        "/usr/bin/borg-e2e"),
    ("rsync",         None,                             None),   # nur Checkboxen
    ("proxmox_hosts", "input[name='pbs_repository']",  "backup@pbs!token@host:store"),
    ("proxmox_jobs",  "input[name='pbs_fingerprint']", "AB:CD:EF"),
    ("proxmox_lxc",   "input[name='backup_storage']",  "e2e-storage"),
]


@pytest.mark.parametrize("module, field_selector, value", MODULES_WITH_SETTINGS)
def test_settings_modal_closes_on_save(page, goto_and_wait_loaded, module, field_selector, value):
    """Einstellungen-Dialog öffnen, speichern – Dialog muss sich schließen."""
    goto_and_wait_loaded(f"/{module}")

    page.click(".page-header-main button[title='Einstellungen']")
    page.wait_for_selector("#settings-modal-backdrop", timeout=10000)

    if field_selector is not None:
        page.fill(f"#settings-modal {field_selector}", value)
    page.click("#settings-modal .btn.btn-primary")

    page.wait_for_selector("#settings-modal-backdrop", state="detached", timeout=10000)
