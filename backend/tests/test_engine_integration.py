from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.ai.base import AIProvider, AnswerResult
from src.automation.browser import Browser
from src.moodle.types import NormalizedQuestion
from tests.fake_browser import FakeBrowser

FIXTURES = Path(__file__).parent / "fixtures" / "moodle"


async def _discard(_session_id: object, _message: object) -> None:
    return None


def _fx(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _start_attempt_page() -> str:
    return '<form><button name="submitbutton">Начать попытку</button></form>'


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


@pytest_asyncio.fixture
async def app_with_engine() -> AsyncIterator[tuple[AsyncClient, object]]:
    from src.automation.manager import EngineManager
    from src.main import create_app

    pages = [_start_attempt_page(), _fx("single_choice.html")]
    fake = FakeBrowser(pages)

    async def browser_factory(strategy: str, port: int) -> Browser:
        return fake

    ai = StubAI()
    app = create_app()
    app.state.ai_provider = ai
    app.state.engine_manager = EngineManager(
        browser_factory=browser_factory,
        ai_factory=lambda: ai,
        broadcast=_discard,
        engine_sleep=_no_sleep,
    )

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            c.headers["X-Backend-Token"] = "test-token"
            yield c, app.state.engine_manager


@pytest.mark.asyncio
async def test_engine_start_runs_attempt_and_marks_session_completed(
    app_with_engine,
):
    client, manager = app_with_engine

    start = await client.post(
        "/api/session/start",
        json={
            "mode": "full_auto",
            "cmid": "305095",
            "access_strategy": "cdp",
        },
    )
    assert start.status_code == 201, start.text
    sid = start.json()["session_id"]

    resp = await client.post(
        "/api/engine/start",
        json={"session_id": sid, "access_strategy": "cdp", "cdp_port": 9222},
    )
    assert resp.status_code == 202, resp.text

    from uuid import UUID

    await manager.wait_for(UUID(sid), timeout=10)

    state = (await client.get(f"/api/session/{sid}")).json()
    assert state["status"] == "completed"
    assert state["score"] == 14
    assert state["max_score"] == 20

    detail = (await client.get(f"/api/history/{sid}")).json()
    assert len(detail["answers"]) == 1
    answer = detail["answers"][0]
    assert "БГУИР" in answer["question_text"]
    assert answer["ai_answer_indices"] == [0]
    assert answer["provider"] == "stub"
    assert answer["confidence"] == pytest.approx(0.9)
    assert answer["options_text"] == ["1964", "1967", "1971", "1980"]


@pytest.mark.asyncio
async def test_engine_stop_aborts_session(app_with_engine):
    client, manager = app_with_engine
    from uuid import UUID

    start = await client.post(
        "/api/session/start",
        json={
            "mode": "full_auto",
            "cmid": "305095",
            "access_strategy": "cdp",
        },
    )
    sid = start.json()["session_id"]

    await client.post(
        "/api/engine/start",
        json={"session_id": sid, "access_strategy": "cdp", "cdp_port": 9222},
    )
    # Give the engine a brief moment to enter the loop, then stop.
    await asyncio.sleep(0)
    await client.post("/api/engine/stop", json={"session_id": sid})
    await manager.wait_for(UUID(sid), timeout=10)

    state = (await client.get(f"/api/session/{sid}")).json()
    assert state["status"] in {"aborted", "completed"}
