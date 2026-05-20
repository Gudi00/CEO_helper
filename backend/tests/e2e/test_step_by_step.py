"""Scenario 2 — step_by_step mode.

The content script shows the modal `.lms-tool-step` with the AI's pick;
the user confirms with Enter (or rejects with Esc). Verifies in real
Chromium that:

* the modal renders with the correct option index and confidence
* Enter triggers a click event on the right `<input>` and Moodle's
  natural radio behaviour leaves `.checked === true`
* Esc dismisses the modal without any input changes
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from tests.e2e.conftest import StubAI, seed_extension_storage


async def _start_session(backend, mode: str = "step_by_step") -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={"mode": mode, "cmid": "305095"},
            headers={"X-Backend-Token": backend["token"]},
        )
        return resp.json()["session_id"]


@pytest.mark.asyncio
async def test_enter_clicks_the_suggested_input(
    mock_moodle, backend_factory, browser_context, extension_id
):
    ai = StubAI(answer_indices=[1], confidence=0.88, reasoning="best match")
    backend = backend_factory(ai=ai)
    sid = await _start_session(backend)
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=sid,
        mode="step_by_step",
    )
    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    modal = page.locator(".lms-tool-step")
    await modal.wait_for(state="attached", timeout=10_000)
    body = (await modal.text_content()) or ""
    # answer_indices=[1] → human label "вариант 2" (1-based) at 88%
    assert "вариант 2" in body
    assert "88%" in body
    assert "best match" in body

    await page.keyboard.press("Enter")
    await modal.wait_for(state="detached", timeout=5_000)

    # The radio for option index 1 should now be checked. Selector mirrors
    # findOptionInput in moodle-parser.ts: r1 row -> input.
    second_radio = page.locator('div.r1 input[type="radio"]')
    await page.wait_for_function(
        "(el) => el?.checked === true",
        arg=await second_radio.element_handle(),
        timeout=5_000,
    )


@pytest.mark.asyncio
async def test_escape_dismisses_modal_without_click(
    mock_moodle, backend_factory, browser_context, extension_id
):
    backend = backend_factory(ai=StubAI(answer_indices=[2], confidence=0.7))
    sid = await _start_session(backend)
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=sid,
        mode="step_by_step",
    )
    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    modal = page.locator(".lms-tool-step")
    await modal.wait_for(state="attached", timeout=10_000)
    await page.keyboard.press("Escape")
    await modal.wait_for(state="detached", timeout=5_000)

    # Give content script a beat to potentially do something (it
    # shouldn't), then verify every radio is still unchecked.
    await asyncio.sleep(0.5)
    any_checked = await page.evaluate(
        """() => Array.from(document.querySelectorAll('div.answer input[type="radio"]'))
                .some(i => i.checked)"""
    )
    assert any_checked is False
