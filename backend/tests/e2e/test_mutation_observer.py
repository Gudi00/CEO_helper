"""Scenario 3 — MutationObserver picks up dynamically-added questions.

Moodle's one-question-per-page layout swaps the `.que` element in place
when "Next page" is pressed. The content script's MutationObserver must
catch new `.que` nodes and process them, while ignoring any already-seen
container (WeakSet `handled`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import FIXTURES, StubAI, seed_extension_storage


@pytest.mark.asyncio
async def test_dom_swap_triggers_second_answer(
    mock_moodle, backend_factory, browser_context, extension_id
):
    ai = StubAI(answer_indices=[2])  # first call: option index 2
    backend = backend_factory(ai=ai)
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
    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    # Wait for the first question to be highlighted.
    first_highlight = page.locator('[data-lms-tool="suggested"]')
    await first_highlight.first.wait_for(state="attached", timeout=10_000)
    assert await first_highlight.count() == 1
    assert ai.calls[0].id == "q739284:1"

    # Now swap the question container — simulating Moodle's "Next page".
    next_html = (FIXTURES / "multiple_choice.html").read_text(encoding="utf-8")
    await page.evaluate(
        """(html) => {
            const old = document.getElementById("question-739284-1");
            if (old) old.remove();
            const tpl = document.createElement("template");
            tpl.innerHTML = html.trim();
            document.body.appendChild(tpl.content.firstElementChild);
        }""",
        next_html,
    )

    # The new question is multiple_choice with 4 options; AI returns [2]
    # which is option index 2 ("JavaScript"). MO should pick it up.
    await page.wait_for_function(
        """() => document.querySelectorAll('[data-lms-tool="suggested"]').length >= 1
                && document.getElementById("question-739284-7")?.querySelector(
                     '[data-lms-tool="suggested"]')""",
        timeout=10_000,
    )

    assert len(ai.calls) == 2
    assert ai.calls[1].id == "q739284:7"
    assert ai.calls[1].type == "multiple_choice"


@pytest.mark.asyncio
async def test_existing_question_not_reprocessed(
    mock_moodle, backend_factory, browser_context, extension_id
):
    """The `handled` WeakSet ensures we don't ask the AI twice if a
    DOM mutation merely touches an already-seen container."""
    ai = StubAI(answer_indices=[0])
    backend = backend_factory(ai=ai)
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
    page = await browser_context.new_page()
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")
    await page.locator('[data-lms-tool="suggested"]').first.wait_for(
        state="attached", timeout=10_000
    )
    assert len(ai.calls) == 1

    # Fire a few DOM mutations near (but not replacing) the question.
    await page.evaluate(
        """() => {
            const host = document.body;
            for (let i = 0; i < 5; i++) {
                const d = document.createElement("div");
                d.className = "noise-" + i;
                host.appendChild(d);
            }
        }"""
    )
    await asyncio.sleep(0.5)
    assert len(ai.calls) == 1  # unchanged
