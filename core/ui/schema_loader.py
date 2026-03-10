"""
core/ui/schema_loader.py  –  Lädt schema.yaml für Create/Edit-Dialoge

Jedes Modul legt neben __init__.py eine schema.yaml ab:

  app/modules/<key>/schema.yaml

Aufbau:
  id_field:          # optionales ID-Feld (nur beim Anlegen angezeigt)
    name: host_id
    label: Host-ID
    placeholder: "..."
    max: 50

  fields:            # Formularfelder
    - name: description
      type: text     # text | number | boolean | select | list
      label: Beschreibung
      row: 1
      column: 1
      ...
"""

import yaml
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=32)
def load_schema(schema_path: str) -> dict:
    """Lädt und cached schema.yaml. Gibt {'id_field': ..., 'fields': [...]} zurück."""
    path = Path(schema_path)
    if not path.exists():
        return {"id_field": None, "fields": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "id_field": data.get("id_field"),
        "fields":   data.get("fields", []),
    }
