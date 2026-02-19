import yaml

def load_schema(module: str):
    with open("templates/partials/create_edit/schemas.yaml", "r") as f:
        data = yaml.safe_load(f)
    return data[module]
