"""
tests/e2e/test_modal_close.py

Prüft dass das Edit-Modal (create_edit_modal.html) sich nach dem Speichern schließt
und dass das Confirm-Modal (confirm_modal.html) sich nach dem Bestätigen schließt.
Testet alle Module die diese Modals verwenden.

Voraussetzung:
    playwright install chromium

Ausführen:
    pytest tests/e2e/test_modal_close.py -v
    pytest tests/e2e/test_modal_close.py -v --headed   # mit Browser-Fenster
"""
import pytest
from playwright.sync_api import Page, expect

# Alle Module die create_edit_modal.html verwenden
MODULES = [
    "borg",
    "rsync",
    "remotes",
    "proxmox_hosts",
    "proxmox_jobs",
    "proxmox_lxc",
]


def _go_to_module(page: Page, base_url: str, module: str) -> None:
    """Navigiert zur Startseite und klickt den Sidebar-Link des Moduls."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    nav_link = page.locator(f'[hx-get="/ui/{module}/content"]')
    if nav_link.count() == 0:
        pytest.skip(f"Kein Sidebar-Link für Modul '{module}' gefunden – ist es registriert?")

    nav_link.first.click()

    # Warten bis #main-content nicht mehr "Laden…" zeigt
    page.wait_for_function(
        "(sel => { const el = document.querySelector(sel); "
        "return el && !el.innerText.includes('Laden'); })('#main-content')",
        timeout=5000,
    )
    # Kurz warten bis Alpine.js und HTMX initialisiert sind
    page.wait_for_timeout(400)


def _find_edit_button(page: Page, module: str):
    """Gibt den ersten Edit-Button des Moduls zurück oder None."""
    btns = page.locator(
        f'button[hx-get*="/ui/{module}/"][hx-get*="/edit"]'
    )
    return btns if btns.count() > 0 else None


def _find_toggle_button(page: Page, module: str):
    """Gibt den ersten Toggle-Button des Moduls zurück oder None."""
    btns = page.locator(
        f'button[hx-get*="/ui/{module}/"][hx-get*="/toggle"]'
    )
    return btns if btns.count() > 0 else None


@pytest.mark.parametrize("module", MODULES)
def test_edit_modal_closes_after_save(page: Page, base_url: str, module: str):
    """
    Öffnet das Edit-Modal des ersten vorhandenen Eintrags,
    klickt Speichern und prüft dass das Modal aus dem DOM entfernt wird.
    """
    _go_to_module(page, base_url, module)

    edit_btns = _find_edit_button(page, module)
    if edit_btns is None:
        pytest.skip(
            f"Modul '{module}' hat keine Einträge – Edit-Modal kann nicht getestet werden."
        )

    # Edit-Modal öffnen
    edit_btns.first.click()

    modal = page.locator("#create-edit-modal")
    expect(modal).to_be_visible(timeout=4000)

    # Speichern-Button klicken (type="button" → JS-gesteuert)
    save_btn = page.locator("#create-edit-submit")
    expect(save_btn).to_be_visible(timeout=2000)
    save_btn.click()

    # Modal muss vollständig aus dem DOM verschwinden
    expect(page.locator("#create-edit-modal")).to_have_count(0, timeout=6000)


@pytest.mark.parametrize("module", MODULES)
def test_edit_modal_opens_correctly(page: Page, base_url: str, module: str):
    """
    Sanity-Check: Edit-Modal öffnet sich überhaupt und zeigt den Speichern-Button.
    """
    _go_to_module(page, base_url, module)

    edit_btns = _find_edit_button(page, module)
    if edit_btns is None:
        pytest.skip(f"Modul '{module}' hat keine Einträge.")

    edit_btns.first.click()

    modal = page.locator("#create-edit-modal")
    expect(modal).to_be_visible(timeout=4000)

    # Speichern-Button vorhanden
    expect(page.locator("#create-edit-submit")).to_be_visible(timeout=2000)

    # Schließen über Escape – Modal muss verschwinden
    page.keyboard.press("Escape")
    expect(page.locator("#create-edit-modal")).to_have_count(0, timeout=3000)


@pytest.mark.parametrize("module", MODULES)
def test_confirm_modal_closes_after_toggle(page: Page, base_url: str, module: str):
    """
    Klickt den Toggle-Switch des ersten Eintrags, bestätigt im Confirm-Modal
    und prüft dass das Confirm-Modal danach aus dem DOM entfernt wird.
    """
    _go_to_module(page, base_url, module)

    toggle_btns = _find_toggle_button(page, module)
    if toggle_btns is None:
        pytest.skip(
            f"Modul '{module}' hat keine Einträge – Confirm-Modal kann nicht getestet werden."
        )

    # Confirm-Modal öffnen
    toggle_btns.first.click()

    confirm_dialog = page.locator(".confirm-dialog")
    expect(confirm_dialog).to_be_visible(timeout=4000)

    # Bestätigen-Button klicken (btn-danger innerhalb des Confirm-Dialogs)
    confirm_btn = confirm_dialog.locator("button.btn-danger")
    expect(confirm_btn).to_be_visible(timeout=2000)
    confirm_btn.click()

    # Confirm-Modal muss vollständig aus dem DOM verschwinden
    expect(page.locator(".confirm-dialog")).to_have_count(0, timeout=6000)


@pytest.mark.parametrize("module", MODULES)
def test_confirm_modal_closes_after_edit_save_then_toggle(
    page: Page, base_url: str, module: str
):
    """
    Öffnet zuerst das Edit-Modal, speichert es, öffnet danach den Toggle-Confirm-Dialog
    und prüft dass dieser sich nach dem Bestätigen ebenfalls schließt.
    """
    _go_to_module(page, base_url, module)

    edit_btns = _find_edit_button(page, module)
    if edit_btns is None:
        pytest.skip(
            f"Modul '{module}' hat keine Einträge – Edit- und Confirm-Modal können nicht getestet werden."
        )

    # Edit-Modal öffnen und speichern
    edit_btns.first.click()
    modal = page.locator("#create-edit-modal")
    expect(modal).to_be_visible(timeout=4000)

    save_btn = page.locator("#create-edit-submit")
    expect(save_btn).to_be_visible(timeout=2000)
    save_btn.click()

    # Edit-Modal muss verschwunden sein bevor wir weitermachen
    expect(page.locator("#create-edit-modal")).to_have_count(0, timeout=6000)

    # Kurz warten bis die Liste neu gerendert ist
    page.wait_for_timeout(400)

    toggle_btns = _find_toggle_button(page, module)
    if toggle_btns is None:
        pytest.skip(
            f"Modul '{module}' hat nach dem Speichern keine Toggle-Buttons mehr."
        )

    # Confirm-Modal öffnen
    toggle_btns.first.click()

    confirm_dialog = page.locator(".confirm-dialog")
    expect(confirm_dialog).to_be_visible(timeout=4000)

    # Bestätigen-Button klicken
    confirm_btn = confirm_dialog.locator("button.btn-danger")
    expect(confirm_btn).to_be_visible(timeout=2000)
    confirm_btn.click()

    # Confirm-Modal muss vollständig aus dem DOM verschwinden
    expect(page.locator(".confirm-dialog")).to_have_count(0, timeout=6000)
