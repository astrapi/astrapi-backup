#ui/modal_routes.py
from flask import render_template, request

from fastapi.responses import RedirectResponse

from .schema_loader import load_schema
from api.storage import get_item
from ui.swagger_utils import ui_tag

def register_modal_routes(app):

    @app.route("/ui/<module>/create")
    @ui_tag("ui")
    def create(module):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")

        schema = load_schema(module)
        submit_url = f"/api/config/{module}/create?container_id={container_id}&loading_id={loading_id}"

        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=schema,
            values=None,
            item=None,
            module=module,
            submit_url=submit_url,
            container_id=container_id,
            loading_id=loading_id
        )

    @app.route("/ui/<module>/<item>/toggle")
    @ui_tag("ui")
    def toggle(module, item):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")
        enabled = request.args.get("enabled")
        description = request.args.get("description")

        verb = "deaktivieren" if enabled else "aktivieren"
        method = "post"
        confirm_url = f"/api/config/{module}/{item}/toggle"

        return render_template(
            "partials/confirm_modal.html",
            description=description,
            verb=verb,
            confirm_url=confirm_url,
            method=method,
            container_id=container_id,
            loading_id=loading_id
        )
        

    @app.route("/ui/<module>/<item>/delete")
    @ui_tag("ui")
    def delete(module, item):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")
        description = request.args.get("description")

        verb = "löschen"
        method = "delete"
        confirm_url = f"/api/config/{module}/{item}/delete"

        return render_template(
            "partials/confirm_modal.html",
            description=description,
            verb=verb,
            confirm_url=confirm_url,
            method=method,
            container_id=container_id,
            loading_id=loading_id
        )

    @app.route("/ui/<module>/<item>/edit")
    @ui_tag("ui")
    def edit(module, item):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")
        enabled = request.args.get("enabled")

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes")

        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")

        schema = load_schema(module)

        values = get_item(module, item)
        if values is None:
            values = {}

        values.setdefault("pre", [])
        values.setdefault("post", [])

        submit_url = (
            f"/api/config/{module}/{item}/edit"
            f"?container_id={container_id}&loading_id={loading_id}"
        )

        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=schema,
            values=values,
            item=item,
            module=module,
            submit_url=submit_url,
            container_id=container_id,
            loading_id=loading_id
        )

    # ── Scheduler ────────────────────────────────────────────────

    @app.route("/ui/scheduler/create")
    @ui_tag("scheduler")
    def scheduler_create():
        return render_template("partials/scheduler/create_modal.html")

    @app.route("/ui/scheduler/<job_id>/edit")
    @ui_tag("scheduler")
    def scheduler_edit(job_id):
        import scheduler.engine as engine
        job = engine.get_job(job_id)
        if job is None:
            return "Job nicht gefunden", 404
        return render_template("partials/scheduler/edit_modal.html", job=job)

    @app.route("/ui/scheduler/<job_id>/delete")
    @ui_tag("scheduler")
    def scheduler_delete(job_id):
        description = request.args.get("description", job_id)
        return render_template(
            "partials/confirm_modal.html",
            description=description, verb="löschen",
            confirm_url=f"/api/scheduler/jobs/{job_id}",
            method="delete",
            container_id="tab-scheduler", loading_id="scheduler-loading"
        )


