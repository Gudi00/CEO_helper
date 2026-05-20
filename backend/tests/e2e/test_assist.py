"""Scenario 1 — assist mode end-to-end.

Real Chromium loads the built extension, the content script attaches to
the mock-Moodle page, parses the question, talks to the real backend
(with a StubAI), and the correct label gets a `data-lms-tool=suggested`
attribute.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.conftest import StubAI, seed_extension_storage


@pytest.mark.asyncio
async def test_assist_highlights_correct_option(
    mock_moodle, backend_factory, browser_context, extension_id
):
    ai = StubAI(answer_indices=[2], confidence=0.91)
    backend = backend_factory(ai=ai)

    # Start a session over HTTP just like the popup would.
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={
                "mode": "assist",
                "cmid": "305095",
                "access_strategy": "extension_native",
            },
            headers={"X-Backend-Token": backend["token"]},
        )
        resp.raise_for_status()
        session_id = resp.json()["session_id"]

    await seed_extension_storage(
        browser_context,
        extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=session_id,
        mode="assist",
    )

    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    # Content script fires async after document_idle → poll for highlight.
    highlighted = page.locator('[data-lms-tool="suggested"], [data-lms-tool="suggested-low"]')
    await highlighted.first.wait_for(state="attached", timeout=10_000)
    count = await highlighted.count()
    assert count == 1

    # The highlighted label should be the third option ("1971") based on
    # single_choice.html and answer_indices=[2].
    text = (await highlighted.first.text_content() or "").strip()
    assert "1971" in text

    # The AI was called exactly once with the parsed question.
    assert len(ai.calls) == 1
    parsed = ai.calls[0]
    assert parsed.type == "single_choice"
    assert "БГУИР" in parsed.text
    assert parsed.metadata.cmid == "305095"


@pytest.mark.asyncio
async def test_assist_uses_low_confidence_variant(
    mock_moodle, backend_factory, browser_context, extension_id
):
    """Confidence < 0.6 → overlay uses the 'suggested-low' variant
    (yellow) so the user knows the AI isn't sure."""
    backend = backend_factory(
        ai=StubAI(answer_indices=[0], confidence=0.4)
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={"mode": "assist", "cmid": "305095"},
            headers={"X-Backend-Token": backend["token"]},
        )
        session_id = resp.json()["session_id"]

    await seed_extension_storage(
        browser_context,
        extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=session_id,
        mode="assist",
    )

    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    low = page.locator('[data-lms-tool="suggested-low"]')
    await low.first.wait_for(state="attached", timeout=10_000)
    assert await low.count() == 1
