import yaml
from pathlib import Path


def load_nav(path: Path) -> list[dict]:
    """Lädt die Navigation aus einer YAML-Datei.

    Einträge können sein:
      - normale Nav-Items (mit key, label, url, icon)
      - Trennlinien: separator: true  (optional group: "Label")
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []

    items: list[dict] = []
    defaults: list[dict] = []

    for entry in raw:
        # Separator / Gruppen-Trenner
        if entry.get("separator"):
            items.append({
                "separator": True,
                "group":     entry.get("group", ""),
            })
            continue

        k = entry.get("key")
        if not k:
            continue

        item = {
            "key":      k,
            "label":    entry.get("label", k.replace("_", " ").title()),
            "url":      entry.get("url", f"/api/ui/{k}/tab"),
            "icon":     entry.get("icon", "home"),
            "default":  bool(entry.get("default", False)),
            "separator": False,
        }

        if item["default"]:
            defaults.append(item)

        items.append(item)

    if len(defaults) > 1:
        raise RuntimeError(
            f"Mehrere Default-Nav-Items gefunden: {[d['key'] for d in defaults]}"
        )

    # Kein explizites Default: erstes nicht-separator Item übernimmt die Rolle
    if not defaults:
        for item in items:
            if not item["separator"]:
                item["default"] = True
                break

    return items
