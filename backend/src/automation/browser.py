"""Browser abstraction for the engine. Lets us test the run-loop without
spinning up a real Chrome instance.

Real implementation (`SeleniumBrowser`) wraps undetected-chromedriver and
runs blocking selenium calls via `asyncio.to_thread`.
"""

from __future__ import annotations

from typing import Protocol


class BrowserError(RuntimeError):
    """Wraps any browser/driver error encountered during automation."""


class Browser(Protocol):
    """Async-friendly browser interface used by the Engine."""

    async def current_url(self) -> str: ...
    async def page_source(self) -> str: ...
    async def navigate(self, url: str) -> None: ...

    async def click_css(self, selector: str) -> None:
        """Find an element by CSS selector and click it.

        Should raise BrowserError when no element is found.
        """

    async def find_text(self, selector: str) -> str:
        """Return the visible text of the first element matching selector."""

    async def scroll_into_view(self, selector: str) -> None:
        """Scroll element into the viewport (smooth, block: center)."""

    async def quit(self) -> None: ...
