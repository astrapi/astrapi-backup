"""Unit-Tests fuer reine Helferfunktionen aus app.modules.borg.api."""

import pytest
from fastapi import HTTPException

from app.modules.borg.api import _sanitize_path, _dir_view, _clean, _extract_lists


class TestSanitizePath:
    def test_sanitize_path_entfernt_leading_slash(self):
        assert _sanitize_path("/etc/backup") == "etc/backup"

    def test_sanitize_path_leerer_pfad_ist_ungueltig(self):
        with pytest.raises(HTTPException) as exc:
            _sanitize_path("   ")
        assert exc.value.status_code == 400

    def test_sanitize_path_blockiert_dotdot(self):
        with pytest.raises(HTTPException) as exc:
            _sanitize_path("../../etc/passwd")
        assert exc.value.status_code == 400


class TestDirView:
    def test_dir_view_liefert_sortierte_verzeichnisse_und_dateien(self):
        entries = [
            {"path": "var/log", "type": "d", "mtime": "2026-03-16T10:00:00"},
            {"path": "var/a.txt", "type": "-", "size": 10, "mtime": "2026-03-16T10:00:00"},
            {"path": "var/b.txt", "type": "-", "size": 20, "mtime": "2026-03-16T10:00:00"},
        ]

        dirs, files = _dir_view(entries, "var")

        assert [d["name"] for d in dirs] == ["log"]
        assert [f["name"] for f in files] == ["a.txt", "b.txt"]


class TestPayloadCleaning:
    def test_clean_entfernt_leere_werte(self):
        data = {
            "description": "job",
            "empty_str": "   ",
            "none_val": None,
            "empty_list": [],
            "enabled": True,
        }

        out = _clean(data)

        assert out == {"description": "job", "enabled": True}

    def test_extract_lists_zieht_listenfelder_aus_form_payload(self):
        schema = {
            "fields": [
                {"name": "description", "type": "text"},
                {"name": "pre", "type": "list"},
                {"name": "post", "type": "list"},
            ]
        }
        payload = {
            "description": "job",
            "pre_1": "echo two",
            "pre_0": "echo one",
        }

        out = _extract_lists(schema, payload)

        assert out["description"] == "job"
        assert out["pre"] == ["echo one", "echo two"]
        assert out["post"] == []
