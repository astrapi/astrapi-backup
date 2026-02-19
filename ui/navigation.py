import yaml
import os

NAV_YAML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "navigation", "items.yaml"
)

def load_nav(path=NAV_YAML_PATH):
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []

    items = []
    defaults = []

    for entry in raw:
        k = entry.get("key")
        if not k:
            continue

        item = {
            "key": k,
            "label": entry.get("label", k.replace("_", " ").title()),
            "url": entry.get("url", f"/api/html/{k}"),
            "icon": entry.get("icon", "default-icon"),
            "default": bool(entry.get("default", False)),
        }

        if item["default"]:
            defaults.append(item)

        items.append(item)

    if len(defaults) > 1:
        raise RuntimeError("Multiple default nav items found")

    return items
