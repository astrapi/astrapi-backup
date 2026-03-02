from flask import Flask, render_template


def make_page(resource_key: str, initial_url: str, nav_items: list[dict]) -> callable:
    """Gibt eine Flask-View zurück, die die App-Shell (index.html) rendert.

    Der HTMX-load-Trigger lädt danach das Tab-Partial via initial_url.
    """
    label = next((it["label"] for it in nav_items if not it.get("separator") and it["key"] == resource_key), None)
    title = label or resource_key.replace("_", " ").title()

    def page():
        return render_template(
            "index.html",
            active_tab=resource_key,
            initial_content_url=initial_url,
            title=title,
        )

    page.__name__ = f"page_{resource_key}"
    return page


def make_tab(resource_key: str, nav_items: list[dict]) -> callable:
    """Gibt eine Flask-View zurück, die nur das Partial rendert (HTMX-Target).

    Das Partial wird unter app/templates/partials/lists/<key>.html erwartet.
    """
    label = next((it["label"] for it in nav_items if not it.get("separator") and it["key"] == resource_key), None)
    title = label or resource_key.replace("_", " ").title()
    list_partial = f"partials/lists/{resource_key}.html"

    def tab():
        return render_template(
            "partials/tab_wrapper.html",
            active_tab=resource_key,
            title=title,
            list_partial=list_partial,
        )

    tab.__name__ = f"tab_{resource_key}"
    return tab


def register_pages(app: Flask, nav_items: list[dict]) -> None:
    """Registriert automatisch Page- und Tab-Route für jeden Nav-Eintrag."""
    for item in nav_items:
        if item.get("separator"):
            continue  # Trennlinien überspringen
        key = item["key"]
        url = item["url"]  # z. B. /api/ui/overview/tab

        app.add_url_rule(
            f"/{key}",
            endpoint=f"page_{key}",
            view_func=make_page(key, url, nav_items),
        )
        app.add_url_rule(
            url,
            endpoint=f"tab_{key}",
            view_func=make_tab(key, nav_items),
        )
