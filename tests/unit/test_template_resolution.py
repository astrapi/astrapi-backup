"""
tests/unit/test_template_resolution.py

Stellt sicher, dass jedes Template, das per TemplateResponse("name", …) in
backupctl/-Code referenziert wird, auch tatsächlich vom Jinja2-Loader aufgelöst
werden kann.

Verhindert Fehler wie:
    jinja2.exceptions.TemplateNotFound: partials/log_modal.html
die erst zur Laufzeit auftreten, weil ein Package umbenannt wurde oder ein
Template-Verzeichnis fehlt.
"""

import ast
from pathlib import Path

import pytest

from backupctl._paths import package_dir

APP_ROOT = package_dir()


# ── Template-Namen aus Quellcode extrahieren ─────────────────────────────────

def _collect_template_names(app_root: Path) -> dict[str, list[str]]:
    """
    Durchsucht alle .py-Dateien unter app_root und gibt ein Dict zurück:
        template_name → Liste von (relpath:zeile)-Strings

    Gesucht wird nach Aufrufen der Form:
        something.TemplateResponse("partials/foo.html", …)
    """
    found: dict[str, list[str]] = {}

    for py_file in app_root.rglob("*.py"):
        if ".venv" in py_file.parts:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        rel = py_file.relative_to(app_root.parent)

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "TemplateResponse"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue

            tpl_name = node.args[0].value
            location = f"{rel}:{node.lineno}"
            found.setdefault(tpl_name, []).append(location)

    return found


# ── Parametrisierter Test ─────────────────────────────────────────────────────

def _template_params():
    names = _collect_template_names(APP_ROOT)
    return [
        pytest.param(name, ", ".join(locs), id=name)
        for name, locs in sorted(names.items())
    ]


@pytest.mark.parametrize("template_name,locations", _template_params())
def test_template_resolvable(template_name: str, locations: str):
    """
    Jedes per TemplateResponse referenzierte Template muss vom Jinja2-Loader
    gefunden werden können.
    """
    from jinja2 import TemplateNotFound
    from backupctl.api.templates import templates

    try:
        templates.env.get_template(template_name)
    except TemplateNotFound:
        locs_fmt = "\n  - ".join(locations.split(", "))
        pytest.fail(
            f"Template '{template_name}' nicht auffindbar.\n"
            f"Referenziert in:\n  - {locs_fmt}\n\n"
            f"Suchpfade des Loaders:\n"
            + _format_loader_paths(templates)
        )


def _format_loader_paths(templates) -> str:
    from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader

    lines = []
    loader = templates.env.loader

    def _walk(ldr, indent=0):
        prefix = "  " * indent
        if isinstance(ldr, ChoiceLoader):
            for sub in ldr.loaders:
                _walk(sub, indent)
        elif isinstance(ldr, PrefixLoader):
            for pfx, sub in ldr.mapping.items():
                if isinstance(sub, FileSystemLoader):
                    for path in sub.searchpath:
                        exists = Path(path).is_dir()
                        lines.append(f"{prefix}[prefix={pfx!r}] {path} {'✓' if exists else '✗ NICHT VORHANDEN'}")
        elif isinstance(ldr, FileSystemLoader):
            for path in ldr.searchpath:
                exists = Path(path).is_dir()
                lines.append(f"{prefix}{path} {'✓' if exists else '✗ NICHT VORHANDEN'}")

    _walk(loader)
    return "\n".join(lines) if lines else "(keine Pfade ermittelbar)"
