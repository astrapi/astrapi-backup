"""Unit-Tests fuer Versionsfunktionen."""
from pathlib import Path

from core.system.version import get_app_version, get_core_version, _read_yaml_version

CORE_ROOT = Path(__file__).resolve().parents[2] / "core"
APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class TestReadYamlVersion:
    def test_liest_vorhandene_version(self, tmp_path):
        path = tmp_path / "version.yaml"
        path.write_text("version: 26.3.1\n", encoding="utf-8")
        assert _read_yaml_version(path) == "26.3.1"

    def test_gibt_default_zurueck_wenn_datei_fehlt(self, tmp_path):
        result = _read_yaml_version(tmp_path / "missing.yaml", default="0.0.0")
        assert result == "0.0.0"


class TestGetVersion:
    def test_liest_app_version_aus_datei(self):
        version = get_app_version(APP_ROOT)
        assert version == "26.3.1"

    def test_liest_core_version_aus_datei(self):
        version = get_core_version(CORE_ROOT)
        assert version == "26.3.3"
