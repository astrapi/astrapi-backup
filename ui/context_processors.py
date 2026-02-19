def inject_common():
    return {"app_name": "backupctl"}

def inject_nav(nav_items):
    default_item = next((it for it in nav_items if it.get("default")), None)
    if default_item is None and nav_items:
        default_item = nav_items[0]

    return {
        "nav_items": nav_items,
        "user": "ottoadm",
        "default_item": default_item
    }
