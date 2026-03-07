# core/ui/swagger_utils.py
#
# Generiert eine OpenAPI-Spec aus den registrierten Flask-Routen
# und stellt /ui/docs + /ui/openapi.json bereit.

from pathlib import Path


def ui_tag(tag_name: str):
    """Decorator: setzt den Swagger-Tag für eine Flask-View."""
    def decorator(func):
        setattr(func, "_ui_tag", tag_name)
        return func
    return decorator


def add_ui_routes_to_spec(app, project_root: Path) -> None:
    """Liest alle Flask-Routen aus und trägt sie in app.apispec ein."""
    skip = {"/ui/docs", "/ui/openapi.json", "/static/<path:filename>"}

    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if rule.rule in skip:
                continue

            methods = [m.lower() for m in rule.methods if m in ("GET", "POST", "DELETE")]
            if not methods:
                continue

            view = app.view_functions.get(rule.endpoint)
            tag  = getattr(view, "_ui_tag", "ui")

            # Quelldatei relativ zum Projekt-Root
            source_file = getattr(getattr(view, "__code__", None), "co_filename", None)
            relative_path = None
            if source_file:
                try:
                    relative_path = str(Path(source_file).resolve().relative_to(project_root))
                except ValueError:
                    relative_path = source_file

            operations = {
                method: {
                    "summary":     f"{method.upper()} {rule.rule}",
                    "description": f"Defined in: {relative_path}" if relative_path else "",
                    "tags":        [tag],
                    "responses":   {"200": {"description": "HTML response"}},
                }
                for method in methods
            }

            # Path-Parameter
            params = [
                {"in": "path", "name": arg, "required": True, "schema": {"type": "string"}}
                for arg in rule.arguments
            ]
            if params:
                for op in operations.values():
                    op["parameters"] = params

            app.apispec._paths[rule.rule] = operations


def register_ui_docs(app, project_root: Path, swagger_html_path: Path) -> None:
    """Registriert /ui/docs und /ui/openapi.json an der Flask-App."""
    from apispec import APISpec
    from flask import jsonify, Response

    app.apispec = APISpec(
        title="backupctl UI-Routen",
        version="1.0.0",
        openapi_version="3.0.2",
        info={"description": "Dokumentation der Flask UI-Routen"},
    )

    @app.route("/ui/docs")
    def ui_docs():
        html = swagger_html_path.read_text(encoding="utf-8")
        html = html.replace("{{OPENAPI_URL}}", "/ui/openapi.json")
        return Response(html, mimetype="text/html")

    @app.route("/ui/openapi.json")
    def ui_openapi_json():
        return jsonify(app.apispec.to_dict())

    # Spec erst befüllen nachdem alle Routen registriert sind
    add_ui_routes_to_spec(app, project_root)
