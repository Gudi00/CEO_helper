"""Scenario 5 — ADR 0007 "Mode A natural stealth" contract.

The extension MUST NOT flip `.checked` on a radio/checkbox directly.
Moodle JS observes change events; a direct property write looks
unnaturally synchronous in logs and bypasses any focus tracking.

We install a Proxy on `HTMLInputElement.prototype` 'checked' setter
BEFORE the content script runs, capture any sets, then run the
step_by_step flow. Native MouseEvent click should still produce
`.checked === true` (because of browser's built-in radio handler),
but the explicit assignment counter must remain at 0.
"""

from __future__ import annotations

import httpx
import pytest

from tests.e2e.conftest import StubAI, seed_extension_storage


@pytest.mark.asyncio
async def test_extension_never_writes_input_checked_directly(
    mock_moodle, backend_factory, browser_context, extension_id
):
    backend = backend_factory(ai=StubAI(answer_indices=[1]))
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{backend['base_url']}/api/session/start",
            json={"mode": "step_by_step", "cmid": "305095"},
            headers={"X-Backend-Token": backend["token"]},
        )
        sid = resp.json()["session_id"]
    await seed_extension_storage(
        browser_context, extension_id,
        backend_url=backend["base_url"],
        backend_token=backend["token"],
        session_id=sid,
        mode="step_by_step",
    )

    page = await browser_context.new_page()

    # Inject the spy at the earliest possible moment for every doc.
    await page.add_init_script(
        """
        (() => {
          const proto = HTMLInputElement.prototype;
          const orig = Object.getOwnPropertyDescriptor(proto, 'checked');
          if (!orig?.set) return;
          window.__lmsCheckedSets = [];
          Object.defineProperty(proto, 'checked', {
            configurable: true,
            enumerable: true,
            get: orig.get,
            set(value) {
              const stack = new Error('checked-set').stack || '';
              // We only flag *explicit* JS writes coming from extension
              // code (chrome-extension://). Native click handlers run
              // in the user agent layer with no JS stack frames pointing
              // at our extension.
              if (stack.includes('chrome-extension://')) {
                (window.__lmsCheckedSets ||= []).push({ value, stack });
              }
              return orig.set.call(this, value);
            },
          });
        })();
        """
    )
    await page.goto(f"{mock_moodle['base_url']}/mod/quiz/attempt.php?cmid=305095")

    modal = page.locator(".lms-tool-step")
    await modal.wait_for(state="attached", timeout=10_000)
    await page.keyboard.press("Enter")
    await modal.wait_for(state="detached", timeout=5_000)

    second_radio = page.locator('div.r1 input[type="radio"]')
    handle = await second_radio.element_handle()
    await page.wait_for_function(
        "(el) => el?.checked === true", arg=handle, timeout=5_000,
    )

    extension_sets = await page.evaluate(
        "window.__lmsCheckedSets ?? []",
    )
    assert extension_sets == [], (
        f"Extension wrote .checked directly: {extension_sets!r}"
    )
