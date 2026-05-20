from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.base import AIProvider, AnswerResult
from src.automation.engine import Engine, EngineEvent
from src.automation.session import Mode, SessionState, Status
from src.moodle.types import NormalizedQuestion
from tests.fake_browser import FakeBrowser

FIXTURES = Path(__file__).parent / "fixtures" / "moodle"


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class StubAI(AIProvider):
    name = "stub"

    def __init__(self, answers: dict[str, list[int]]) -> None:
        self._answers = answers
        self.calls: list[NormalizedQuestion] = []

    async def answer(self, question: NormalizedQuestion) -> AnswerResult:
        self.calls.append(question)
        # Default to first option when an answer isn't pre-scripted.
        indices = self._answers.get(question.id, [0])
        return AnswerResult(
            answer_indices=indices,
            confidence=0.9,
            reasoning="stub",
            provider="stub",
            from_cache=False,
        )


async def _no_sleep(_: float) -> None:
    return None


def _start_attempt_page() -> str:
    return (
        '<form><button name="submitbutton">Начать попытку</button></form>'
    )


@pytest.fixture
def state() -> SessionState:
    return SessionState(
        mode=Mode.FULL_AUTO, cmid="305095", status=Status.RUNNING
    )


@pytest.mark.asyncio
async def test_engine_runs_single_page_to_submission(state):
    pages = [
        _start_attempt_page(),
        _fx("single_choice.html"),  # quiz page (no next button → submit)
    ]
    browser = FakeBrowser(pages)
    ai = StubAI(answers={"q739284:1": [0]})

    events: list[EngineEvent] = []

    async def collect(ev: EngineEvent) -> None:
        events.append(ev)

    engine = Engine(
        browser=browser, ai=ai, cmid="305095",
        on_event=collect, sleep=_no_sleep,
    )
    await engine.run(state)

    assert state.status is Status.COMPLETED
    assert state.questions_answered == 1
    assert ai.calls[0].id == "q739284:1"

    event_types = [e.type for e in events]
    assert event_types == [
        "question_loaded",
        "answer_suggested",
        "engine_clicked",
        "attempt_completed",
    ]
    # question_loaded payload must carry the full serialized question so
    # the manager can persist it without a separate DB lookup.
    q_loaded = next(e for e in events if e.type == "question_loaded")
    assert q_loaded.payload["question"]["id"] == "q739284:1"
    assert q_loaded.payload["question"]["hash"]
    assert len(q_loaded.payload["question"]["options"]) == 4
    completed = events[-1].payload
    assert completed["score"] == 14
    assert completed["max_score"] == 20

    clicks = browser.clicks
    assert clicks[0].endswith('submitbutton"]') or "submitbutton" in clicks[0]
    # The actual radio click selector targets question container + r0.
    radio_click = next(c for c in clicks if "r0" in c)
    assert "question-739284-1" in radio_click
    assert any("finish" in c or "finishattempt" in c for c in clicks)
    assert 'button[name="confirm"]' in clicks


@pytest.mark.asyncio
async def test_engine_traverses_multiple_pages(state):
    pages = [
        _start_attempt_page(),
        # Page 1: single question with a "next" button present.
        _fx("single_choice.html")
        + '<input class="mod_quiz-next-nav" type="submit" value="next">',
        # Page 2: a different question, no next button → triggers submit.
        _fx("multiple_choice.html"),
    ]
    browser = FakeBrowser(pages)
    ai = StubAI(answers={"q739284:1": [2], "q739284:7": [0, 2]})

    engine = Engine(browser=browser, ai=ai, cmid="305095", sleep=_no_sleep)
    await engine.run(state)

    assert state.status is Status.COMPLETED
    assert state.questions_answered == 2
    # Two question_ids passed through AI.
    assert [c.id for c in ai.calls] == ["q739284:1", "q739284:7"]
    # Multi-choice → two radio clicks recorded on that page.
    multi_clicks = [c for c in browser.clicks if "question-739284-7" in c]
    assert len(multi_clicks) == 2


@pytest.mark.asyncio
async def test_engine_stop_aborts_before_submit(state):
    # Two quiz pages: if stop fires on the first question, the second
    # page should never be visited and no submit should occur.
    pages = [
        _start_attempt_page(),
        _fx("single_choice.html")
        + '<input class="mod_quiz-next-nav" type="submit" value="Next">',
        _fx("multiple_choice.html"),
    ]
    browser = FakeBrowser(pages)

    class OneShotStopAI(AIProvider):
        name = "stop"

        def __init__(self) -> None:
            self.calls = 0

        async def answer(self, question):
            self.calls += 1
            await engine.stop()
            return AnswerResult(
                answer_indices=[0], confidence=0.5, reasoning=None,
                provider="stop", from_cache=False,
            )

    ai = OneShotStopAI()
    engine = Engine(browser=browser, ai=ai, cmid="305095", sleep=_no_sleep)
    await engine.run(state)

    assert state.status is Status.ABORTED
    assert ai.calls == 1
    clicks = browser.clicks
    assert not any("finishattempt" in c or "finish-nav" in c for c in clicks)
    assert 'button[name="confirm"]' not in clicks
