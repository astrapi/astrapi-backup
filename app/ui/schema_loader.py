# ui/schema_loader.py
import yaml
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "templates" / "partials" / "create_edit" / "schemas.yaml"

def load_schema(module: str):
    with open(_SCHEMA_PATH, "r") as f:
        data = yaml.safe_load(f)
    return data[module]
