"""Fixtures for the end-to-end tests (FR74).

Each test module gets its own application server with a fresh SQLite database and the demo
data, so modules cannot affect each other (for example through login throttling). Every test
fails if the page reports a JavaScript error or a Content Security Policy violation (FR55).

    cd e2e && pytest                       # uses Playwright's own Chromium
    E2E_CHROMIUM_EXECUTABLE=/path/to/chrome pytest   # or a specific browser binary
"""

import functools
import http.server
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DEMO_PASSWORDS = {"admin": "admin123", "alice": "alice123", "bob": "bob12345"}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_healthy(url: str, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early:\n{process.stdout.read()}")
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Server did not become healthy in time")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Start the real application (uvicorn) on a free port with demo data."""
    data = tmp_path_factory.mktemp("shop")
    port = _free_port()
    env = {
        **os.environ,
        "SHOP_DATABASE_URL": f"sqlite:///{data / 'shop.db'}",
        "SHOP_UPLOAD_DIR": str(data / "uploads"),
        "SHOP_SEED_DEMO_DATA": "1",
        "SHOP_COOKIE_SECURE": "0",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(url, process)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def other_origin():
    """A static page on a different origin, playing the attacker in CSRF tests (FR52)."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(__file__).parent / "attacker"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # "localhost" vs "127.0.0.1": a different site, not just a different port.
    yield f"http://localhost:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    executable = os.environ.get("E2E_CHROMIUM_EXECUTABLE")
    return {**browser_type_launch_args, **({"executable_path": executable} if executable else {})}


@pytest.fixture(autouse=True)
def page_problems(page: Page):
    """Collect JavaScript errors and CSP violations; fail the test if there are any."""
    problems: list[str] = []
    page.add_init_script(
        "document.addEventListener('securitypolicyviolation',"
        " e => console.error('CSP violation: ' + e.violatedDirective + ' ' + e.blockedURI))"
    )
    page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
    page.on("console", lambda msg: problems.append(msg.text) if msg.text.startswith("CSP violation") else None)
    yield problems
    assert problems == []


class Shop:
    """Helpers for driving the shop in a test."""

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.url = base_url

    def goto(self, path: str) -> None:
        self.page.goto(self.url + path)

    def login(self, username: str, role: str = "customer", password: str | None = None) -> None:
        self.goto("/")
        if role == "admin":
            self.page.click("[data-role=admin]")
        self.page.fill("#username", username)
        self.page.fill("#password", password or DEMO_PASSWORDS[username])
        self.page.click("#login-btn")
        self.page.wait_for_url("**/admin.html" if role == "admin" else "**/shop.html")

    def logout(self) -> None:
        self.page.click("#logout-btn")
        self.page.wait_for_url("**/index.html")

    def after_api(self, url_part: str, action) -> None:
        """Run `action` and wait until the API call containing `url_part` has answered and the page re-rendered."""
        with self.page.expect_response(lambda response: url_part in response.url):
            action()
        self.page.wait_for_timeout(100)

    def card_names(self) -> list[str]:
        return self.page.locator(".product-card .name").all_inner_texts()

    def text(self, selector: str) -> str:
        return " | ".join(part.strip() for part in self.page.locator(selector).inner_text().splitlines() if part.strip())


@pytest.fixture
def shop(page: Page, server: str) -> Shop:
    page.set_default_timeout(10_000)
    return Shop(page, server)
