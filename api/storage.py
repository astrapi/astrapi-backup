import yaml
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

def _path(name: str) -> Path:
    return CONFIG_DIR / f"{name}.yaml"

def load_config(name: str) -> Dict[str, Any]:
    path = _path(name)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(name: str, data: Dict[str, Any]) -> None:
    print(data)
    p = _path(name)
    # Falls None übergeben wird, schreibe eine leere Mapping‑Datei
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise TypeError("save_config erwartet ein dict als 'data'")
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

def get_item(name: str, item_id: str) -> Optional[Dict[str, Any]]:
    if item_id is None:
        return None

    cfg = load_config(name) or {}

    # 1) exakter String-Match
    if item_id in cfg:
        return cfg[item_id]

    # 2) int-Match
    try:
        item_int = int(item_id)
        if item_int in cfg:
            return cfg[item_int]
    except ValueError:
        pass

    return None


def save_item(name: str, item_id, item: dict) -> None:
    if item is None:
        raise TypeError("item darf nicht None sein")
    if not isinstance(item, dict):
        raise TypeError("item muss ein dict sein")

    cfg = load_config(name) or {}

    # 🔥 WICHTIG: NICHT mit alten Daten mergen!
    cfg[item_id] = item

    save_config(name, cfg)



def delete_item(name: str, item_id: str) -> bool:
    cfg = load_config(name) or {}
    item_key = str(item_id).strip()
    # direktes Match
    if item_key in cfg:
        cfg.pop(item_key)
        save_config(name, cfg)
        return True
    # fallback: stringified keys vergleichen
    for k in list(cfg.keys()):
        if str(k).strip() == item_key:
            cfg.pop(k)
            save_config(name, cfg)
            return True
    return False
