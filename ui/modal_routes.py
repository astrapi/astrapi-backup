from flask import render_template, request

from .schema_loader import load_schema
from api.storage import load_config

def register_modal_routes(app):

    @app.route("/ui/<module>/create")
    def open_create_modal(module):
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

    @app.route("/ui/<module>/xxx")
    def open_edit_modal(module):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")
        item = request.args.get("item")
        
        schema = load_schema(module)

        # 1) Konfiguration laden
        cfg = load_config(module)

        # 2) Werte des Items extrahieren
        if item not in cfg:
            return f"Item '{item}' not found in module '{module}'", 404

        values = cfg[item]

        submit_url = (
            f"/api/config/{module}/edit"
            f"?container_id={container_id}&loading_id={loading_id}"
        )

        return render_template(
            "partials/create_edit/create_edit_modal.html",
            schema=schema,
            values=None,     # <-- HIER!
            item=item,         # <-- wichtig für Titel
            module=module,
            submit_url=submit_url,
            container_id=container_id,
            loading_id=loading_id
        )


    @app.route("/confirm/<module>/<item>/<action>")
    def confirm_action(module, item, action):
        container_id = request.args.get("container_id")
        loading_id = request.args.get("loading_id")
        enabled = request.args.get("enabled")
        description = request.args.get("description")

        if isinstance(enabled, str):
            enabled = enabled.lower() in ("1", "true", "yes")

        if action == "toggle":
            verb = "deaktivieren" if enabled else "aktivieren"
            method = "post"
            confirm_url = f"/api/config/{module}/{item}/toggle"

        elif action == "delete":
            verb = "löschen"
            method = "delete"
            confirm_url = f"/api/config/{module}/{item}"

        elif action == "edit":
            container_id = request.args.get("container_id")
            loading_id = request.args.get("loading_id")
            item = request.args.get("item")
            
            schema = load_schema(module)

            # 1) Konfiguration laden
            # cfg = load_config(module)

            # 2) Werte des Items extrahieren
            # if item not in cfg:
            #     return f"Item '{item}' not found in module '{module}'", 404

            # values = cfg[item]

            submit_url = (
                f"/api/config/{module}/edit"
                f"?container_id={container_id}&loading_id={loading_id}"
            )

            return render_template(
                "partials/create_edit/create_edit_modal.html",
                schema=schema,
                values=None,     # <-- HIER!
                item=item,         # <-- wichtig für Titel
                module=module,
                submit_url=submit_url,
                container_id=container_id,
                loading_id=loading_id
            )

        return render_template(
            "partials/confirm_modal.html",
            description=description,
            verb=verb,
            confirm_url=confirm_url,
            method=method,
            container_id=container_id,
            loading_id=loading_id
        )
