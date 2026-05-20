"""Full-auto engine. Runs the quiz from start to submit using a Browser
implementation. See ADR 0006 / 0007.

The run-loop is browser-agnostic (`Browser` Protocol). Real automation lives
in `selenium_browser.py` under the `[engine]` extra. Unit tests inject a
FakeBrowser to verify the loop without a real Chrome instance.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.ai.base import AIProvider
from src.automation.browser import Browser, BrowserError
from src.automation.session import SessionState, Status
from src.moodle.parser import parse_questions
from src.moodle.types import NormalizedQuestion
from src.stealth.delays import (
    before_submit_s,
    between_clicks_s,
    between_pages_s,
    reading_delay_s,
)

logger = logging.getLogger(__name__)

# Moodle 4.x button selectors (see ADR 0008).
SEL_START_ATTEMPT = 'button[name="submitbutton"], input[name="submitbutton"]'
SEL_NEXT_PAGE = 'input.mod_quiz-next-nav, button[name="next"]'
SEL_FINISH_ATTEMPT = (
    'input.mod_quiz-finish-nav, button[name="finishattempt"]'
)
SEL_CONFIRM_SUBMIT = 'button[name="confirm"]'
SEL_SCORE = ".quizattemptcounts, table.quizreviewsummary"

_RE_SCORE_PAIR = re.compile(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)")


@dataclass
class EngineEvent:
    """Lightweight event the engine emits via the provided callback.

    Maps onto the WS protocol's server→client events (see ws-protocol.md).
    """

    type: str
    payload: dict


EventCallback = Callable[[EngineEvent], Awaitable[None]]


async def _noop_callback(_: EngineEvent) -> None:
    return None


class Engine:
    def __init__(
        self,
        *,
        browser: Browser,
        ai: AIProvider,
        cmid: str,
        on_event: EventCallback = _noop_callback,
        max_pages: int = 200,
        # Skip random delays in unit tests by injecting zero-sleep callable.
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._browser = browser
        self._ai = ai
        self._cmid = cmid
        self._on_event = on_event
        self._max_pages = max_pages
        self._sleep = sleep
        self._stopped = False

    async def stop(self) -> None:
        self._stopped = True

    async def run(self, state: SessionState) -> None:
        score: int | None = None
        max_score: int | None = None
        try:
            await self._start_attempt()
            await self._loop_pages(state)
            if self._stopped:
                state.abort()
                return
            score, max_score = await self._submit()
        except BrowserError as exc:
            logger.exception("engine browser error")
            state.fail()
            await self._on_event(
                EngineEvent(
                    type="error",
                    payload={
                        "code": "ENGINE_BROWSER_FAILED",
                        "message": str(exc),
                        "fatal": True,
                    },
                )
            )
            raise
        finally:
            await self._browser.quit()

        state.complete()
        await self._on_event(
            EngineEvent(
                type="attempt_completed",
                payload={
                    "session_id": str(state.id),
                    "score": score,
                    "max_score": max_score,
                },
            )
        )

    async def _start_attempt(self) -> None:
        # Caller is expected to have navigated to the quiz view page.
        # We just click "Пройти тест" / "Начать попытку" sequence.
        await self._click(SEL_START_ATTEMPT)
        await self._sleep(between_pages_s())

    async def _loop_pages(self, state: SessionState) -> None:
        for _ in range(self._max_pages):
            if self._stopped or state.status is not Status.RUNNING:
                return
            html = await self._browser.page_source()
            questions = parse_questions(
                html, cmid=self._cmid, page_number=state.current_page
            )
            for q in questions:
                if self._stopped:
                    return
                await self._handle_question(q, state)

            if await self._has_next_page():
                await self._click(SEL_NEXT_PAGE)
                state.advance_page()
                await self._sleep(between_pages_s())
            else:
                return

    async def _handle_question(
        self,
        question: NormalizedQuestion,
        state: SessionState,
    ) -> None:
        await self._on_event(
            EngineEvent(
                type="question_loaded",
                payload={
                    "question_id": question.id,
                    "page_number": question.metadata.page_number,
                    # Full question is included so the manager can persist
                    # it; the WS broadcaster strips it before forwarding.
                    "question": question.model_dump(),
                },
            )
        )

        result = await self._ai.answer(question)
        await self._on_event(
            EngineEvent(
                type="answer_suggested",
                payload={
                    "question_id": question.id,
                    "answer_indices": result.answer_indices,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "provider": result.provider,
                    "from_cache": result.from_cache,
                },
            )
        )

        await self._sleep(reading_delay_s(len(question.text)))

        for option_index in result.answer_indices:
            selector = _option_selector(question, option_index)
            await self._browser.scroll_into_view(selector)
            await self._sleep(0.2)
            await self._click(selector)
            await self._on_event(
                EngineEvent(
                    type="engine_clicked",
                    payload={
                        "question_id": question.id,
                        "option_index": option_index,
                    },
                )
            )
            await self._sleep(between_clicks_s())

        state.mark_answered()

    async def _has_next_page(self) -> bool:
        html = await self._browser.page_source()
        return ("mod_quiz-next-nav" in html) or ('name="next"' in html)

    async def _submit(self) -> tuple[int | None, int | None]:
        await self._click(SEL_FINISH_ATTEMPT)
        await self._sleep(before_submit_s())
        await self._click(SEL_CONFIRM_SUBMIT)
        await self._sleep(between_pages_s())
        return await self._read_score()

    async def _read_score(self) -> tuple[int | None, int | None]:
        try:
            text = await self._browser.find_text(SEL_SCORE)
        except BrowserError:
            return None, None
        match = _RE_SCORE_PAIR.search(text)
        if not match:
            return None, None
        score = _to_int(match.group(1))
        max_score = _to_int(match.group(2))
        return score, max_score

    async def _click(self, selector: str) -> None:
        try:
            await self._browser.scroll_into_view(selector)
            await self._sleep(0.2)
            await self._browser.click_css(selector)
        except BrowserError:
            raise


def _option_selector(question: NormalizedQuestion, option_index: int) -> str:
    attempt_id = question.metadata.attempt_id
    q_num = question.id.split(":")[1]
    container = f"div#question-{attempt_id}-{q_num}"
    return f"{container} .answer > div.r{option_index} input"


def _to_int(s: str) -> int:
    # Moodle scores can be "14,00" / "14.00" / "14".
    cleaned = s.replace(",", ".")
    try:
        return int(round(float(cleaned)))
    except ValueError:
        return 0
