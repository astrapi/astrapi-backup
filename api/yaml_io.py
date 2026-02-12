import yaml
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

def load_yaml(name: str):
    path = CONFIG_DIR / f"{name}.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)

