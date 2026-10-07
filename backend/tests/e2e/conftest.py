"""Shared fixtures for the Playwright-driven end-to-end suite.

What this gives every e2e test:

* `mock_moodle` — ASGI app + thread serving Moodle-shaped HTML on a free port
* `backend` — our real FastAPI app with an injected StubAI on another free port
* `e2e_extension_dir` — a copy of `extension/dist` with manifest patched to
  allow our localhost mock-Moodle URL (so the content script actually loads)
* `browser_context` — a persistent Chromium context with the extension loaded
* `extension_id` — the dynamic chrome-extension://<id> we get after launch

The two web servers run in threads (no subprocess) so tests can poke the
backend's `app.state` directly to inject a StubAI before lifespan runs.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from playwright.async_api import BrowserContext, async_playwright
from uvicorn import Config, Server

from src.ai.base import AIProvider, AnswerResult
from src.automation.manager import EngineManager
from src.moodle.types import NormalizedQuestion

# --- root paths ---------------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]
EXTENSION_DIST = ROOT / "extension" / "dist"
FIXTURES = ROOT / "backend" / "tests" / "fixtures" / "moodle"


async def _discard(_session_id: object, _message: object) -> None:
    return None


def pytest_collection_modifyitems(config, items):
    """Auto-mark every test in this directory as `e2e`."""
    here = Path(__file__).parent
    for item in items:
        try:
            if Path(item.fspath).is_relative_to(here):
                item.add_marker(pytest.mark.e2e)
        except (ValueError, AttributeError):
            continue


# --- low-level helpers --------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _run_server_in_thread(app: Any, port: int) -> tuple[Server, threading.Thread]:
    config = Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = Server(config)

    def _run() -> None:
        asyncio.run(server.serve())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    deadline = time.time() + 10.0
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError(f"server did not start within 10s (port {port})")
        time.sleep(0.05)
    return server, thread


def _stop_server(server: Server) -> None:
    server.should_exit = True


# --- AI stubs -----------------------------------------------------------


class StubAI(AIProvider):
    """Deterministic AI for tests; defaults to answer_indices=[0]."""

    def __init__(
        self,
        *,
        answer_indices: list[int] | None = None,
        confidence: float = 0.92,
        reasoning: str = "stub",
        on_call: Callable[[NormalizedQuestion], None] | None = None,
    ) -> None:
        self.name = "stub-ai"
        self._answer_indices = answer_indices or [0]
        self._confidence = confidence
        self._reasoning = reasoning
        self._on_call = on_call
        self.calls: list[NormalizedQuestion] = []

    async def answer(self, question: NormalizedQuestion) -> AnswerResult:
        self.calls.append(question)
        if self._on_call:
            self._on_call(question)
        return AnswerResult(
            answer_indices=self._answer_indices,
            confidence=self._confidence,
            reasoning=self._reasoning,
            provider="stub-ai",
            from_cache=False,
            latency_ms=1,
        )


# --- mock Moodle --------------------------------------------------------


@pytest.fixture
def mock_moodle() -> Iterator[dict[str, Any]]:
    """Returns dict with `.base_url`, `.state` (mutable html), `.port`."""
    from tests.e2e.mock_moodle import create_mock_app

    initial = (FIXTURES / "single_choice.html").read_text(encoding="utf-8")
    app, state = create_mock_app(initial)
    port = _free_port()
    server, _thread = _run_server_in_thread(app, port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        yield {"base_url": base_url, "state": state, "port": port}
    finally:
        _stop_server(server)


# --- real backend with injected StubAI ----------------------------------


@pytest.fixture
def backend_factory(tmp_path, monkeypatch) -> Callable[..., dict[str, Any]]:
    """Returns a factory: `backend = factory(ai=StubAI())`.

    Sets DATABASE_URL to a per-test SQLite file. Builds a fresh FastAPI app
    so each test gets isolation and can swap AI / engine_manager.
    """

    def _make(ai: AIProvider | None = None) -> dict[str, Any]:
        db_path = tmp_path / "backend.db"
        monkeypatch.setenv(
            "DATABASE_URL", f"sqlite+aiosqlite:///{db_path}"
        )
        monkeypatch.setenv("BACKEND_TOKEN", "test-token")
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("OLLAMA_ENABLED", "false")

        from src.config import get_settings
        get_settings.cache_clear()
        import src.persistence.db as db_mod
        db_mod._engine = None
        db_mod._session_factory = None

        from src.main import create_app

        app = create_app()
        ai = ai or StubAI()
        app.state.ai_provider = ai

        async def _no_sleep(_: float) -> None:
            return None

        app.state.engine_manager = EngineManager(
            browser_factory=_failing_browser_factory,
            ai_factory=lambda: ai,
            broadcast=_discard,
            engine_sleep=_no_sleep,
        )

        port = _free_port()
        server, _thread = _run_server_in_thread(app, port)
        base_url = f"http://127.0.0.1:{port}"
        return {
            "app": app,
            "ai": ai,
            "port": port,
            "base_url": base_url,
            "server": server,
            "token": "test-token",
        }

    started: list[dict[str, Any]] = []

    def factory(ai: AIProvider | None = None) -> dict[str, Any]:
        info = _make(ai)
        started.append(info)
        return info

    yield factory

    for info in started:
        _stop_server(info["server"])


async def _failing_browser_factory(strategy: str, port: int):
    raise RuntimeError(
        "default browser_factory not used in e2e — override per test"
    )


# --- extension dist patched for localhost -------------------------------


@pytest.fixture
def e2e_extension_dir(tmp_path, mock_moodle) -> Path:
    """Copy dist/ to tmp + patch manifest to also match the mock host.

    Real prod manifest only matches `https://lms.bsuir.by/mod/quiz/*`.
    We extend it for tests by appending `http://127.0.0.1:<port>/mod/quiz/*`
    so the content script actually fires on our mock.
    """
    if not EXTENSION_DIST.exists():
        pytest.skip("extension/dist not built — run `cd extension && npm run build`")
    dest = tmp_path / "ext"
    shutil.copytree(EXTENSION_DIST, dest)
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    port = mock_moodle["port"]
    # content_scripts: only inject on the mock quiz path (specific port).
    manifest["content_scripts"][0]["matches"].append(
        f"http://127.0.0.1:{port}/mod/quiz/*"
    )
    # host_permissions: omit explicit port so cross-origin fetches reach
    # any localhost service. Chrome match patterns without a port match
    # ALL ports on that host — covers mock-moodle + backend on different
    # random ports.
    manifest["host_permissions"].append("http://127.0.0.1/*")
    if "web_accessible_resources" in manifest:
        for rule in manifest["web_accessible_resources"]:
            rule.setdefault("matches", []).append(
                f"http://127.0.0.1:{port}/*"
            )
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return dest


# --- chromium with extension loaded -------------------------------------


@pytest_asyncio.fixture
async def browser_context(
    tmp_path, e2e_extension_dir
) -> AsyncIterator[BrowserContext]:
    """Persistent context (required for MV3 extensions in Playwright)."""
    user_data = tmp_path / "userdata"
    user_data.mkdir()
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data),
            headless=False,
            args=[
                f"--disable-extensions-except={e2e_extension_dir}",
                f"--load-extension={e2e_extension_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=DisableLoadExtensionCommandLineSwitch",
            ],
        )
        try:
            yield ctx
        finally:
            await ctx.close()


@pytest_asyncio.fixture
async def extension_id(browser_context: BrowserContext) -> str:
    """Discover the chrome-extension://<id> we just loaded."""
    # MV3 background service worker may take a moment to appear.
    if browser_context.service_workers:
        sw = browser_context.service_workers[0]
    else:
        sw = await browser_context.wait_for_event(
            "serviceworker", timeout=10000
        )
    # url like chrome-extension://abcdef.../service-worker-loader.js
    parts = sw.url.split("/")
    if len(parts) < 3 or parts[0] != "chrome-extension:":
        raise RuntimeError(f"unexpected sw url: {sw.url}")
    return parts[2]


async def seed_extension_storage(
    browser_context: BrowserContext,
    extension_id: str,
    *,
    backend_url: str,
    backend_token: str,
    session_id: str | None,
    mode: str = "assist",
    show_overlay: bool = True,
) -> None:
    """Pre-populate chrome.storage.local from the popup page context.

    Service-worker MV3 has chrome.storage too, but opening the popup is
    easier from Playwright since we get a normal Page.
    """
    page = await browser_context.new_page()
    await page.goto(f"chrome-extension://{extension_id}/src/popup/index.html")
    payload = {
        "backendUrl": backend_url,
        "backendToken": backend_token,
        "mode": mode,
        "showOverlay": show_overlay,
    }
    if session_id is not None:
        payload["activeSessionId"] = session_id
    await page.evaluate(
        """async (data) => { await chrome.storage.local.set(data); }""",
        payload,
    )
    await page.close()
