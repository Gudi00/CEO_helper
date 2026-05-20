"""Scenario 6 — popup degrades gracefully when the backend is offline.

Without a running backend, the popup's `/api/health` probe must fail
cleanly: the status bar shows an "offline" hint, no exception bubbles to
the page, the extension keeps responding to user input.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from tests.e2e.conftest import seed_extension_storage


def _surely_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_popup_shows_offline_status_without_backend(
    mock_moodle, browser_context, extension_id
):
    # No backend at all — point popup at a free (dead) port.
    dead_port = _surely_free_port()
    dead_url = f"http://127.0.0.1:{dead_port}"
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=dead_url,
        backend_token="anything",
        session_id=None,
        mode="assist",
    )

    page = await browser_context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(f"chrome-extension://{extension_id}/src/popup/index.html")

    status = page.locator("#status")
    await status.wait_for(state="attached", timeout=5_000)
    # Health probe is async — give it a moment.
    await page.wait_for_function(
        """() => {
            const el = document.getElementById('status');
            return el && el.textContent && el.textContent.includes('offline');
        }""",
        timeout=10_000,
    )
    text = (await status.text_content()) or ""
    assert "offline" in text.lower()

    # No unhandled JS errors should bubble up.
    assert errors == []

    # Form inputs remain interactive.
    cmid = page.locator("#cmid")
    await cmid.fill("305095")
    assert await cmid.input_value() == "305095"


@pytest.mark.asyncio
async def test_start_button_reports_error_when_backend_is_offline(
    browser_context, extension_id
):
    dead_port = _surely_free_port()
    dead_url = f"http://127.0.0.1:{dead_port}"
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=dead_url,
        backend_token="t",
        session_id=None,
        mode="assist",
    )
    page = await browser_context.new_page()
    await page.goto(f"chrome-extension://{extension_id}/src/popup/index.html")

    await page.locator("#cmid").fill("305095")
    await page.locator("#start").click()
    # Wait for the status to indicate failure (any non-OK message after
    # the start attempt is made — backend is dead, so this must surface).
    await page.wait_for_function(
        """() => {
            const el = document.getElementById('status');
            const t = el?.textContent || '';
            return /стартовать|offline/i.test(t);
        }""",
        timeout=10_000,
    )
    status_text = (await page.locator("#status").text_content()) or ""
    assert any(s in status_text for s in ("Не удалось стартовать", "offline"))

    # Give it ~1s — there must NOT be infinite retry storming, indicated by
    # the popup remaining responsive and the status not flipping back to
    # "ok".
    await asyncio.sleep(1.0)
    final = (await page.locator("#status").text_content()) or ""
    assert "ok" not in final.lower()
