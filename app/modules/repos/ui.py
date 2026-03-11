# app/modules/repos/ui.py
from flask import Blueprint, render_template, request

from helpers.secrets import get_secret_safe, set_secret
from core.ui.settings_registry import get_module as get_setting, set_module

KEY = "repos"
bp  = Blueprint(f"{KEY}_ui", __name__)

# ── Schemas für die generischen Modals ────────────────────────────────────────

_CREATE_SCHEMA = [
    {"name": "action",      "type": "select",   "label": "Aktion",
     "options": [
         {"value": "init",   "label": "Neu anlegen (borg init)"},
         {"value": "import", "label": "Bestehendes importieren"},
     ],
     "required": True, "column": 1, "row": 1},
    {"name": "name",        "type": "text",     "label": "Name",
     "placeholder": "z.B. home-backup",      "max": 100, "required": True, "column": 2, "row": 1},
    {"name": "path",        "type": "text",     "label": "Pfad",
     "placeholder": "/mnt/borg/repo",        "max": 500, "required": True, "mono": True,
     "column": 1, "row": 2},
    {"name": "description", "type": "text",     "label": "Beschreibung",
     "placeholder": "Optionale Beschreibung", "max": 200, "column": 2, "row": 2},
    {"name": "encryption",  "type": "select",   "label": "Verschlüsselung",
     "options": [
         {"value": "repokey-blake2", "label": "repokey-blake2 (empfohlen)"},
         {"value": "repokey",        "label": "repokey"},
         {"value": "keyfile-blake2", "label": "keyfile-blake2"},
         {"value": "none",           "label": "keine"},
     ],
     "required": True, "column": 1, "row": 3},
    {"name": "passphrase",  "type": "password", "label": "Passphrase",
     "placeholder": "Passphrase für dieses Repository", "column": 2, "row": 3},
]

_EDIT_SCHEMA = [
    {"name": "name",        "type": "text",     "label": "Name",
     "max": 100, "required": True, "column": 1, "row": 1},
    {"name": "path",        "type": "text",     "label": "Pfad",
     "max": 500, "required": True, "mono": True, "column": 2, "row": 1},
    {"name": "description", "type": "text",     "label": "Beschreibung",
     "max": 200, "column": 1, "row": 2},
    {"name": "passphrase",  "type": "password", "label": "Passphrase",
     "placeholder": "leer lassen = nicht ändern", "column": 2, "row": 2},
]


# ── Einstellungen (Settings-Modal) ────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/settings", methods=["GET", "POST"])
def settings_modal():
    from core.ui.module_registry import _mod_registry
    mod = _mod_registry.get(KEY)
    if mod is None:
        return "", 404

    saved = False
    if request.method == "POST":
        form = request.form.to_dict()
        passphrase = form.pop("borg_passphrase", "").strip()
        if passphrase:
            set_secret("BORG_PASSPHRASE", passphrase)
        for k, v in form.items():
            set_module(KEY, k, v)
        saved = True

    values = {
        field["key"]: get_setting(KEY, field["key"], field.get("default", ""))
        for field in mod.settings_schema
        if field.get("type") != "password"
    }
    return render_template(
        "partials/settings_modal.html",
        mod=mod,
        schema=mod.settings_schema,
        values=values,
        saved=saved,
    )

# ── Content (Listenpartial) ───────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/content")
def content():
    from modules.repos.api import _repos_cfg
    return render_template("partials/list_wrapper.html",
        cfg=_repos_cfg(),
        module=KEY,
        container_id=f"tab-{KEY}",
        loading_id=f"{KEY}-loading",
        content_template=f"{KEY}/partials/list.html",
        has_toggle=False,
        has_run_buttons=False,
        running={},
    )


# ── Anlegen-Modal ─────────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/create")
def create_modal():
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=_CREATE_SCHEMA,
        id_field=None,
        item=None,
        submit_url=f"/api/{KEY}/create",
        method="post",
        title="Repository hinzufügen",
        loading_id=f"{KEY}-loading",
        container_id=f"tab-{KEY}",
    )


# ── Bearbeiten-Modal ──────────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<int:repo_id>/edit")
def edit_modal(repo_id: int):
    from api.storage import get_repo
    repo = get_repo(repo_id)
    if not repo:
        return "Repo nicht gefunden", 404
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=_EDIT_SCHEMA,
        id_field=None,
        item=repo,
        submit_url=f"/api/{KEY}/{repo_id}/edit",
        method="post",
        title=f"Repository bearbeiten – {repo['name']}",
        loading_id=f"{KEY}-loading",
        container_id=f"tab-{KEY}",
    )


# ── Löschen-Bestätigung ───────────────────────────────────────────────────────

@bp.route(f"/ui/{KEY}/<int:repo_id>/delete")
def delete_modal(repo_id: int):
    from api.storage import get_repo
    repo = get_repo(repo_id) or {}
    return render_template(
        "partials/confirm_modal.html",
        description=repo.get("name", str(repo_id)),
        verb="aus der Liste entfernen",
        confirm_url=f"/api/{KEY}/{repo_id}",
        method="delete",
        reload_url=f"/ui/{KEY}/content",
        container_id=request.args.get("container_id", f"tab-{KEY}"),
        loading_id=request.args.get("loading_id", f"{KEY}-loading"),
    )
