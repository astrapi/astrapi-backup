from __future__ import annotations

import importlib
import os
import shutil
import socket
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

import pytest
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"


@pytest.fixture(scope="session")
def e2e_enabled() -> None:
    if os.getenv("RUN_E2E") != "1":
        pytest.skip("E2E-Tests sind deaktiviert. Mit RUN_E2E=1 aktivieren.")


@pytest.fixture
def e2e_asgi_app(e2e_enabled, loaded_modules, tmp_path, monkeypatch):
    api_storage = importlib.import_module("api.storage")
    monkeypatch.setattr(api_storage, "DB_PATH", tmp_path / "backupctl-e2e.db")
    if getattr(api_storage._local, "conn", None):
        api_storage._local.conn.close()
        delattr(api_storage._local, "conn")

    ui_storage = importlib.import_module("core.ui.storage")
    settings_registry = importlib.import_module("core.ui.settings_registry")
    ui_app = importlib.import_module("core.ui.app")
    scheduler_engine = importlib.import_module("core.modules.scheduler.engine")

    monkeypatch.setattr(ui_app, "storage_init", lambda _app_root: ui_storage.init(tmp_path))
    monkeypatch.setattr(ui_app, "settings_init", lambda _app_root: settings_registry.init(tmp_path))
    monkeypatch.setattr(scheduler_engine, "init", lambda: None)

    create_api = importlib.import_module("app.api.fastapi_app").create
    create_ui = importlib.import_module("core.ui").create

    api = create_api(modules=loaded_modules)
    ui = create_ui(app_root=APP_ROOT, modules=loaded_modules)

    @api.get("/__e2e__/ping", response_class=HTMLResponse)
    def _ping() -> str:
        return "ok"

    core_static = PROJECT_ROOT / "core" / "ui" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/", WSGIMiddleware(ui))
    return api


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_for_port(host: str, port: int, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server auf {host}:{port} wurde nicht rechtzeitig erreichbar")


@pytest.fixture
def live_server_url(e2e_asgi_app) -> Iterator[str]:
    host = "127.0.0.1"
    port = _find_free_port()
    config = uvicorn.Config(e2e_asgi_app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(host, port)

    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser(e2e_enabled):
    playwright = pytest.importorskip("playwright.sync_api", reason="playwright nicht installiert")
    try:
        with playwright.sync_playwright() as p:
            # Prefer local/system browser to avoid flaky CDN downloads in CI/offline setups.
            executable = (
                os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
                or shutil.which("chromium")
                or shutil.which("chromium-browser")
                or shutil.which("google-chrome")
                or shutil.which("google-chrome-stable")
            )
            launch_kwargs = {"headless": True}
            if executable:
                launch_kwargs["executable_path"] = executable

            browser = p.chromium.launch(**launch_kwargs)
            yield browser
            browser.close()
    except Exception as exc:
        pytest.skip(f"Chromium fuer Playwright konnte nicht gestartet werden: {exc}")


@pytest.fixture
def page(browser, live_server_url):
    context = browser.new_context(base_url=live_server_url, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def goto_and_wait_loaded(page) -> Callable[[str], None]:
    """Navigiert zu einem Pfad und wartet bis der Inhalt vollständig geladen ist."""
    def _impl(path: str) -> None:
        page.goto(path, wait_until="domcontentloaded")
        try:
            page.wait_for_function("() => typeof window.htmx !== 'undefined'", timeout=8000)
        except Exception as exc:
            pytest.skip(f"HTMX wurde nicht geladen (vermutlich ohne Internet/CDN): {exc}")
        page.wait_for_selector("#main-content", timeout=10000)
        page.wait_for_function(
            """
            () => {
                const el = document.querySelector('#main-content');
                if (!el) return false;
                return !el.innerText.includes('Laden');
            }
            """,
            timeout=10000,
        )

    return _impl
