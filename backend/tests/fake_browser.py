"""Scripted Browser implementation for unit testing the engine.

Pages are queued; each click whose selector matches a known
page-advance pattern pops the next page. Click selectors are recorded so
tests can assert exactly which buttons were pressed and in which order.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from src.automation.browser import Browser, BrowserError

# Substrings that indicate the click should advance to the next page.
PAGE_ADVANCE_PATTERNS = (
    "mod_quiz-next-nav",
    'name="next"',
    'name="submitbutton"',  # Start attempt button
)
CONFIRM_PATTERN = 'name="confirm"'


class FakeBrowser(Browser):
    def __init__(
        self,
        pages: Iterable[str],
        *,
        score_text: str = "Оценка 14,00/20,00",
    ) -> None:
        self._pages: deque[str] = deque(pages)
        if not self._pages:
            raise ValueError("FakeBrowser needs at least one page")
        self._current_page = self._pages.popleft()
        self._score_text = score_text
        self.clicks: list[str] = []
        self.scrolled: list[str] = []
        self._current_url = "https://lms.example/mod/quiz/view.php"

    async def current_url(self) -> str:
        return self._current_url

    async def page_source(self) -> str:
        return self._current_page

    async def navigate(self, url: str) -> None:
        self._current_url = url

    async def click_css(self, selector: str) -> None:
        self.clicks.append(selector)
        if CONFIRM_PATTERN in selector:
            self._current_page = (
                f'<div class="quizattemptcounts">{self._score_text}</div>'
            )
            return
        if any(p in selector for p in PAGE_ADVANCE_PATTERNS):
            if self._pages:
                self._current_page = self._pages.popleft()
            # Else: stay on current page; engine should detect "no next"
            # and proceed to submission.

    async def find_text(self, selector: str) -> str:
        if "quizattemptcounts" in selector or "quizreviewsummary" in selector:
            return self._score_text
        raise BrowserError(f"unknown selector {selector!r}")

    async def scroll_into_view(self, selector: str) -> None:
        self.scrolled.append(selector)

    async def quit(self) -> None:
        self._pages.clear()
