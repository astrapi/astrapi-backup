from flask import render_template
#from ui.swagger_utils import ui_tag

def make_page(resource_key, initial_url, list_partial=None, title=None, nav_items=None):
    if list_partial is None:
        list_partial = f"partials/lists/{resource_key}.html"

    if title is None:
        label = next((it["label"] for it in nav_items if it["key"] == resource_key), None)
        title = label or resource_key.replace("_", " ").title()

    def page():
        context = {
            "active_tab": resource_key,
            "initial_content_url": initial_url,
            "title": title,
            "endpoint": initial_url,
            "container_id": f"tab-{resource_key}",
            "loading_id": f"{resource_key}-loading",
            "list_partial": list_partial,
        }
        return render_template("index.html", **context)

    page.__name__ = f"page_{resource_key}"
    return page


def register_pages(app, nav_items):
    for item in nav_items:
        key = item["key"]
        url = item["url"]
        view = make_page(key, url, nav_items=nav_items)
        setattr(view, "_ui_tag", "pages")
        app.add_url_rule(f"/{key}", endpoint=f"page_{key}", view_func=view)
