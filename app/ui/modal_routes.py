# ui/modal_routes.py
from flask import render_template, request
from .schema_loader import load_schema
from api.storage import get_item


def register_modal_routes(app):

    # ── Modul-Modals (create / edit / toggle / delete) ───────────────────────

    @app.route("/ui/<module>/create")
    def ui_create(module):
        container_id = request.args.get("container_id")
        loading_id   = request.args.get("loading_id")
        schema       = load_schema(module)
        submit_url   = f"/api/config/{module}/create?container_id={container_id}&loading_id={loading_id}"
        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=schema, values=None, item=None,
            module=module, submit_url=submit_url,
            container_id=container_id, loading_id=loading_id,
        )

    @app.route("/ui/<module>/<item>/toggle")
    def ui_toggle(module, item):
        container_id = request.args.get("container_id")
        loading_id   = request.args.get("loading_id")
        enabled      = request.args.get("enabled")
        description  = request.args.get("description")
        verb         = "deaktivieren" if enabled == "True" else "aktivieren"
        return render_template(
            "partials/confirm_modal.html",
            description=description, verb=verb,
            confirm_url=f"/api/config/{module}/{item}/toggle",
            method="post",
            container_id=container_id, loading_id=loading_id,
        )

    @app.route("/ui/<module>/<item>/delete")
    def ui_delete(module, item):
        container_id = request.args.get("container_id")
        loading_id   = request.args.get("loading_id")
        description  = request.args.get("description")
        return render_template(
            "partials/confirm_modal.html",
            description=description, verb="löschen",
            confirm_url=f"/api/config/{module}/{item}/delete",
            method="delete",
            container_id=container_id, loading_id=loading_id,
        )

    @app.route("/ui/<module>/<item>/edit")
    def ui_edit(module, item):
        container_id = request.args.get("container_id")
        loading_id   = request.args.get("loading_id")
        schema       = load_schema(module)
        values       = get_item(module, item) or {}
        values.setdefault("pre", [])
        values.setdefault("post", [])
        values.setdefault("exclude", [])
        submit_url = (
            f"/api/config/{module}/{item}/edit"
            f"?container_id={container_id}&loading_id={loading_id}"
        )
        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=schema, values=values, item=item,
            module=module, submit_url=submit_url,
            container_id=container_id, loading_id=loading_id,
        )

    # ── Scheduler-Modals ─────────────────────────────────────────────────────

    @app.route("/ui/scheduler/create")
    def scheduler_create():
        return render_template("partials/scheduler/create_modal.html")

    @app.route("/ui/scheduler/<job_id>/edit")
    def scheduler_edit(job_id):
        import scheduler.engine as engine
        job = engine.get_job(job_id)
        if job is None:
            return "Job nicht gefunden", 404
        return render_template("partials/scheduler/edit_modal.html", job=job)

    @app.route("/ui/scheduler/<job_id>/delete")
    def scheduler_delete(job_id):
        description = request.args.get("description", job_id)
        return render_template(
            "partials/confirm_modal.html",
            description=description, verb="löschen",
            confirm_url=f"/api/scheduler/jobs/{job_id}",
            method="delete",
            container_id="tab-scheduler", loading_id="scheduler-loading",
        )
