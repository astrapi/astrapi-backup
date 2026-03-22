"""
tests/e2e/conftest.py

Startet den App-Server für E2E-Tests falls er nicht bereits läuft.

Verwendung:
    # Server bereits gestartet:
    pytest tests/e2e/

    # Server automatisch starten:
    pytest tests/e2e/          # startet auf Port 5001

    # Anderen Port verwenden:
    E2E_PORT=8080 pytest tests/e2e/
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORT = int(os.environ.get("E2E_PORT", 5001))
BASE_URL = f"http://localhost:{DEFAULT_PORT}"


def _server_is_up(url: str, timeout: float = 2.0) -> bool:
    try:
        httpx.get(url, timeout=timeout)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def base_url() -> str:
    """Gibt die Base-URL zurück (pytest-playwright nutzt diese automatisch)."""
    return BASE_URL


@pytest.fixture(scope="session", autouse=True)
def ensure_server(base_url: str):
    """Startet den Server falls er noch nicht läuft, beendet ihn nach den Tests."""
    if _server_is_up(base_url):
        yield base_url
        return

    proc = subprocess.Popen(
        [sys.executable, "main.py", "--no-reload", "--port", str(DEFAULT_PORT)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(30):
        time.sleep(0.5)
        if _server_is_up(base_url):
            break
    else:
        proc.terminate()
        pytest.fail(f"Server auf {base_url} hat nicht rechtzeitig geantwortet.")

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)
