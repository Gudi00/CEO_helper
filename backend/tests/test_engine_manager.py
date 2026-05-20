"""Unit tests for EngineManager lifecycle and event handling, in isolation
from FastAPI / HTTP."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.ai.base import AIProvider, AnswerResult
from src.automation.browser import Browser
from src.automation.manager import (
    EngineAlreadyRunning,
    EngineManager,
    EngineNotRunning,
)
from src.moodle.types import NormalizedQuestion
from src.persistence import Session, get_session
from src.persistence.db import init_db
from tests.fake_browser import FakeBrowser
from tests.test_engine import _fx, _start_attempt_page


class StubAI(AIProvider):
    name = "stub"

    async def answer(self, question: NormalizedQuestion) -> AnswerResult:
        return AnswerResult(
            answer_indices=[0],
            confidence=0.9,
            reasoning=None,
            provider="stub",
            from_cache=False,
        )


async def _no_sleep(_: float) -> None:
    return None


async def _seed_session(session_id: UUID, cmid: str = "305095") -> None:
    async with get_session() as db:
        db.add(
            Session(
                id=session_id,
                mode="full_auto",
                access_strategy="cdp",
                cmid=cmid,
                ai_provider_primary="stub",
                status="running",
            )
        )


def _make_manager(
    fake: FakeBrowser, *, broadcast: list[dict[str, Any]] | None = None
) -> EngineManager:
    captured = broadcast if broadcast is not None else []

    async def _broadcast(session_id: UUID, msg: dict[str, Any]) -> None:
        captured.append(msg)

    async def _browser_factory(strategy: str, port: int) -> Browser:
        return fake

    return EngineManager(
        browser_factory=_browser_factory,
        ai_factory=StubAI,
        broadcast=_broadcast,
        engine_sleep=_no_sleep,
    )


@pytest.mark.asyncio
async def test_manager_runs_attempt_and_persists_question_and_answer():
    await init_db()
    sid = uuid4()
    await _seed_session(sid)

    fake = FakeBrowser([_start_attempt_page(), _fx("single_choice.html")])
    broadcast: list[dict[str, Any]] = []
    mgr = _make_manager(fake, broadcast=broadcast)

    await mgr.start(
        session_id=sid, cmid="305095", access_strategy="cdp", cdp_port=9222
    )
    await mgr.wait_for(sid, timeout=10)

    # WS messages should never carry the full question object.
    for msg in broadcast:
        assert "question" not in msg

    msg_types = [m["type"] for m in broadcast]
    assert "question_loaded" in msg_types
    assert "answer_suggested" in msg_types
    assert msg_types[-1] == "attempt_completed"

    # DB sanity: question + answer rows + session updated.
    from sqlalchemy import select
    from src.persistence import Answer, Question

    async with get_session() as db:
        questions = (await db.execute(select(Question))).scalars().all()
        answers = (await db.execute(select(Answer))).scalars().all()
        session = await db.get(Session, sid)

    assert len(questions) == 1
    assert "БГУИР" in questions[0].text
    assert len(answers) == 1
    assert answers[0].answer_indices_json == [0]
    assert session is not None
    assert session.status == "completed"
    assert session.score == 14
    assert session.max_score == 20


@pytest.mark.asyncio
async def test_manager_start_twice_for_same_session_raises():
    await init_db()
    sid = uuid4()
    await _seed_session(sid)
    fake = FakeBrowser([_start_attempt_page(), _fx("single_choice.html")])
    mgr = _make_manager(fake)

    await mgr.start(
        session_id=sid, cmid="305095", access_strategy="cdp", cdp_port=9222
    )
    try:
        with pytest.raises(EngineAlreadyRunning):
            await mgr.start(
                session_id=sid,
                cmid="305095",
                access_strategy="cdp",
                cdp_port=9222,
            )
    finally:
        await mgr.wait_for(sid, timeout=10)


@pytest.mark.asyncio
async def test_manager_stop_on_unknown_session_raises():
    mgr = _make_manager(FakeBrowser(["<div></div>"]))
    with pytest.raises(EngineNotRunning):
        await mgr.stop(uuid4())


@pytest.mark.asyncio
async def test_manager_is_running_flag_toggles():
    await init_db()
    sid = uuid4()
    await _seed_session(sid)
    fake = FakeBrowser([_start_attempt_page(), _fx("single_choice.html")])
    mgr = _make_manager(fake)

    assert mgr.is_running(sid) is False
    await mgr.start(
        session_id=sid, cmid="305095", access_strategy="cdp", cdp_port=9222
    )
    assert mgr.is_running(sid) is True
    await mgr.wait_for(sid, timeout=10)
    assert mgr.is_running(sid) is False
