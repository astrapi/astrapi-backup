"""
core/ui/storage.py  –  AstrapiFlaskUi V3  Zentrale Storage-Klasse

Generischer YAML-backed Key-Value Store für alle Module.
Daten werden in app/data/<collection>.yaml gespeichert.

Verwendung in einem Modul:
    from core.ui.storage import YamlStorage
    store = YamlStorage("hosts")          # → app/data/hosts.yaml

    store.list()                          # dict aller Einträge
    store.get("web-01")                   # einzelner Eintrag oder None
    store.create("web-01", {...})         # neu anlegen
    store.update("web-01", {...})         # vorhandenen Eintrag aktualisieren
    store.delete("web-01")               # löschen
    store.toggle("web-01")               # enabled-Flag umschalten

Schreibzugriff ausschließlich über API-Endpunkte —
nie direkt aus Templates oder anderen UI-Schichten aufrufen.

Init (einmalig beim App-Start notwendig):
    YamlStorage.init(app_root)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
import yaml

_DATA_DIR: Path | None = None


class StorageNotInitialized(RuntimeError):
    pass


def init(app_root: Path) -> None:
    """Setzt das Datenverzeichnis. Muss vor der ersten Nutzung aufgerufen werden.

    Wird automatisch von core/ui/app.py beim Start aufgerufen.
    """
    global _DATA_DIR
    _DATA_DIR = app_root / "data"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


class YamlStorage:
    """Generischer YAML-backed Storage für eine Collection.

    Args:
        collection: Name der Collection (= Dateiname ohne .yaml)
        seed_data:  Optionale Startdaten wenn die Datei noch nicht existiert

    Beispiel:
        store = YamlStorage("hosts", seed_data={"web-01": {...}})
    """

    def __init__(self, collection: str, seed_data: dict | None = None):
        self.collection = collection
        self._seed      = seed_data or {}
        self._lock      = threading.Lock()

    @property
    def _path(self) -> Path:
        if _DATA_DIR is None:
            raise StorageNotInitialized(
                "YamlStorage.init(app_root) wurde noch nicht aufgerufen. "
                "Stelle sicher dass core.ui.create() vor der ersten Storage-Nutzung läuft."
            )
        return _DATA_DIR / f"{self.collection}.yaml"

    # ── Lesen ─────────────────────────────────────────────────────────────────

    def list(self) -> dict:
        """Gibt alle Einträge zurück."""
        with self._lock:
            if not self._path.exists():
                if self._seed:
                    self._write(self._seed)
                return dict(self._seed)
            return self._read()

    def get(self, key: str) -> dict | None:
        """Gibt einen einzelnen Eintrag zurück, oder None wenn nicht gefunden."""
        with self._lock:
            return self._read().get(key)

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._read()

    # ── Schreiben (nur über API-Endpunkte aufrufen) ───────────────────────────

    def create(self, key: str, values: dict) -> dict:
        """Legt einen neuen Eintrag an. Wirft KeyError wenn key bereits existiert."""
        with self._lock:
            data = self._read()
            if key in data:
                raise KeyError(f"'{key}' existiert bereits in '{self.collection}'")
            data[key] = values
            self._write(data)
            return data[key]

    def update(self, key: str, values: dict) -> dict:
        """Aktualisiert einen vorhandenen Eintrag. Wirft KeyError wenn nicht gefunden."""
        with self._lock:
            data = self._read()
            if key not in data:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            data[key].update(values)
            self._write(data)
            return data[key]

    def upsert(self, key: str, values: dict) -> dict:
        """Legt an oder aktualisiert – create + update kombiniert."""
        with self._lock:
            data = self._read()
            if key in data:
                data[key].update(values)
            else:
                data[key] = values
            self._write(data)
            return data[key]

    def delete(self, key: str) -> None:
        """Löscht einen Eintrag. Wirft KeyError wenn nicht gefunden."""
        with self._lock:
            data = self._read()
            if key not in data:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            del data[key]
            self._write(data)

    def toggle(self, key: str, field: str = "enabled") -> bool:
        """Schaltet ein Boolean-Feld um. Gibt den neuen Wert zurück."""
        with self._lock:
            data = self._read()
            if key not in data:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            current = bool(data[key].get(field, True))
            data[key][field] = not current
            self._write(data)
            return data[key][field]

    # ── Interne Helfer ────────────────────────────────────────────────────────

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _write(self, data: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def __repr__(self) -> str:
        return f"YamlStorage(collection={self.collection!r}, path={self._path})"
