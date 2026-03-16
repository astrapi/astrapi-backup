"""Integrationstests fuer Borg-UI-Modal-Routen (Flask + Templates)."""


def test_create_modal_oeffnet_formular(flask_ui_client):
    response = flask_ui_client.get("/ui/borg/create")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "create-edit-modal" in html
    assert "create-edit-form" in html
    assert "Borg Job anlegen" in html


def test_edit_modal_oeffnet_formular_mit_bestehenden_werten(flask_ui_client, monkeypatch):
    monkeypatch.setattr(
        "api.storage.get_item",
        lambda module, item: {
            "description": "Nightly Backup",
            "enabled": True,
            "pre": ["echo pre"],
            "post": ["echo post"],
            "exclude": ["/tmp"],
        },
    )

    response = flask_ui_client.get("/ui/borg/42/edit")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "create-edit-modal" in html
    assert "Borg Job bearbeiten" in html
    assert "Nightly Backup" in html


def test_toggle_modal_liefert_confirm_url(flask_ui_client):
    response = flask_ui_client.get("/ui/borg/42/toggle?enabled=True&description=Nightly")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/api/borg/42/toggle" in html


def test_delete_modal_liefert_confirm_url(flask_ui_client):
    response = flask_ui_client.get("/ui/borg/42/delete?description=Nightly")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "/api/borg/42/delete" in html
