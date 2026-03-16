from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
CORE_TEMPLATES = PROJECT_ROOT / "core" / "ui" / "templates"
APP_TEMPLATES = APP_ROOT / "templates"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


@pytest.fixture
def loaded_modules(tmp_path):
    from core.ui import settings_registry
    from core.ui.module_registry import _mod_registry, load_modules
    from core.ui.storage import YamlStorage

    _mod_registry.clear()
    settings_registry._registry.reset()
    settings_registry.init(tmp_path)
    YamlStorage.reset()
    YamlStorage.init(tmp_path)
    return load_modules(APP_ROOT)


@pytest.fixture
def flask_ui_app(loaded_modules):
    from core.ui.module_registry import register_flask_modules
    from api.templates import (
        _module_card_actions,
        _module_has_settings,
        _module_label,
    )

    app = Flask(
        __name__,
        template_folder=str(CORE_TEMPLATES),
    )
    app.config.update(TESTING=True, LOADED_MODULES=loaded_modules)

    loaders = []
    if APP_TEMPLATES.exists():
        loaders.append(FileSystemLoader(str(APP_TEMPLATES)))
    loaders.append(FileSystemLoader(str(CORE_TEMPLATES)))
    register_flask_modules(app, loaded_modules, loaders)
    app.jinja_env.loader = ChoiceLoader(loaders)
    app.jinja_env.globals["module_label"] = _module_label
    app.jinja_env.globals["module_has_settings"] = _module_has_settings
    app.jinja_env.globals["module_card_actions"] = _module_card_actions
    return app


@pytest.fixture
def flask_ui_client(flask_ui_app):
    return flask_ui_app.test_client()


@pytest.fixture
def fastapi_app(loaded_modules):
    from core.ui.module_registry import register_fastapi_modules

    app = FastAPI()
    register_fastapi_modules(app, loaded_modules)
    return app


@pytest.fixture
def api_client(fastapi_app):
    return TestClient(fastapi_app)
