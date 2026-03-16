from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

NAV_PATHS = [
    "/borg",
    "/rsync",
    "/proxmox_hosts",
    "/proxmox_jobs",
    "/proxmox_lxc",
    "/remotes",
    "/history",
    "/errors",
    "/notify",
    "/scheduler",
    "/settings",
    "/sysinfo",
]


def test_can_navigate_through_all_main_modules(page, goto_and_wait_loaded):
    goto_and_wait_loaded("/borg")

    for path in NAV_PATHS[1:]:
        key = path.lstrip("/")
        page.click(f"#nav-{key}")
        page.wait_for_url(f"**{path}", timeout=10000)
        page.wait_for_selector("#main-content", timeout=10000)
        assert page.locator("#main-content").inner_text().strip() != ""


def test_borg_create_save_closes_modal_and_persists(page, goto_and_wait_loaded):
    goto_and_wait_loaded("/borg")

    page.click("button[title='Neu']")
    page.wait_for_selector("#create-edit-modal", timeout=10000)

    page.fill("#create-edit-form input[name='description']", "E2E Borg Job")
    page.click("#create-edit-submit")

    page.wait_for_selector("#create-edit-modal", state="detached", timeout=10000)
    page.wait_for_selector("article.ds-card", timeout=10000)
    assert "E2E Borg Job" in page.locator("#main-content").inner_text()


def test_borg_edit_toggle_delete_journey(page, goto_and_wait_loaded):
    goto_and_wait_loaded("/borg")

    page.click("button[title='Neu']")
    page.fill("#create-edit-form input[name='description']", "E2E Original")
    page.click("#create-edit-submit")
    page.wait_for_selector("#create-edit-modal", state="detached", timeout=10000)

    card = page.locator("article.ds-card", has_text="E2E Original").first
    card.locator("button[title='Bearbeiten']").click()
    page.wait_for_selector("#create-edit-modal", timeout=10000)
    page.fill("#create-edit-form input[name='description']", "E2E Geaendert")
    page.click("#create-edit-submit")
    page.wait_for_selector("#create-edit-modal", state="detached", timeout=10000)
    assert page.locator("article.ds-card", has_text="E2E Geaendert").count() == 1

    card = page.locator("article.ds-card", has_text="E2E Geaendert").first
    card.locator("button.toggle-switch").click()
    page.wait_for_selector(".confirm-dialog", timeout=10000)
    page.locator(".confirm-dialog .btn-danger").click()
    page.wait_for_selector(".confirm-dialog", state="detached", timeout=10000)
    page.wait_for_timeout(250)
    assert "off" in page.locator("article.ds-card", has_text="E2E Geaendert").first.get_attribute("class")

    card.locator(".btn-icon-danger").last.click()
    page.wait_for_selector(".confirm-dialog", timeout=10000)
    page.locator(".confirm-dialog .btn-danger").click()
    page.wait_for_selector(".confirm-dialog", state="detached", timeout=10000)
    page.wait_for_timeout(250)
    assert page.locator("article.ds-card", has_text="E2E Geaendert").count() == 0


def test_notify_channel_create_and_modal_close(page, goto_and_wait_loaded):
    goto_and_wait_loaded("/notify")

    page.click("button:has-text('Neuer Kanal')")
    page.wait_for_selector("#backend-select-modal", timeout=10000)
    page.click("#backend-select-modal .bk-card.bk-ntfy")

    page.wait_for_selector("#channel-modal", timeout=10000)
    page.fill("#ch-modal-form input[name='label']", "E2E Notify")
    page.fill("#ch-modal-form input[name='ntfy_topic']", "backupctl-e2e")
    page.click("#channel-modal .btn.btn-primary")

    page.wait_for_selector("#channel-modal", state="detached", timeout=10000)
    assert "E2E Notify" in page.locator("#main-content").inner_text()
