"""Regression for the bug the user hit in real Chrome:

The quiz page can finish loading BEFORE the user opens the popup and
clicks Start. Earlier the content script marked every visible `.que`
as handled in that scenario and never re-processed them — so the
extension appeared dead.

Fix: handled-tracking is now per-(container, sessionId). The content
script also listens to `chrome.storage.onChanged` and re-runs over all
visible questions when `activeSessionId` appears.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.conftest import StubAI, seed_extension_storage


@pytest.mark.asyncio
async def test_question_processed_after_late_session_start(
    mock_moodle, backend_factory, browser_context, extension_id
):
    ai = StubAI(answer_indices=[2])
    backend = backend_factory(ai=ai)
    # Seed storage without activeSessionId — content script will fire
    # but should NOT mark the container as handled.
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=None,
        mode="assist",
    )
    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    # Quick beat — the content script's bootstrap should run and bail
    # (no session). The question must NOT be highlighted yet.
    await page.wait_for_function(
        "() => document.querySelectorAll('div.que[id^=\"question-\"]').length === 1",
        timeout=10_000,
    )
    suggested = page.locator('[data-lms-tool="suggested"]')
    assert await suggested.count() == 0
    assert len(ai.calls) == 0

    # Now simulate "user opens popup and clicks Start": create a session
    # on the backend, then push activeSessionId into chrome.storage.
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={"mode": "assist", "cmid": "305095"},
            headers={"X-Backend-Token": backend["token"]},
        )
        sid = resp.json()["session_id"]
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=sid,
        mode="assist",
    )

    # Content script's storage listener should pick this up and finally
    # process the already-visible question.
    await suggested.first.wait_for(state="attached", timeout=10_000)
    assert await suggested.count() == 1
    assert len(ai.calls) == 1
    assert ai.calls[0].id == "q739284:1"


@pytest.mark.asyncio
async def test_backend_error_shows_toast(
    mock_moodle, backend_factory, browser_context, extension_id
):
    """When the backend rejects an answer call, the content script must
    surface a visible toast (not just a console error)."""
    backend = backend_factory(ai=StubAI())  # AI is fine
    # Seed an INVALID token so the backend returns 401.
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token="wrong-token",
        session_id=None,
        mode="assist",
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={"mode": "assist", "cmid": "305095"},
            headers={"X-Backend-Token": backend["token"]},
        )
        sid = resp.json()["session_id"]
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token="wrong-token",
        session_id=sid,
        mode="assist",
    )

    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    toast = page.locator(".lms-tool-toast.lms-tool-toast--err")
    await toast.wait_for(state="attached", timeout=10_000)
    text = (await toast.text_content()) or ""
    assert "INVALID_TOKEN" in text or "backend error" in text.lower()
