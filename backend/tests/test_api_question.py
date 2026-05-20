"""Tests for the assist-route /api/question/answer (extension-mode).

Verifies: AI invocation, response shape, persistence into Question/Answer
tables, cache reuse on repeated hash, feedback endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.ai.base import AIProvider, AnswerResult, InvalidResponse
from src.moodle.hashing import compute_question_hash
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata
from src.persistence import Answer, Question, get_session


class StubAI(AIProvider):
    name = "stub"

    def __init__(
        self,
        *,
        answer_indices: list[int] | None = None,
        confidence: float = 0.9,
        raise_exc: Exception | None = None,
    ) -> None:
        self._answer_indices = answer_indices or [0]
        self._confidence = confidence
        self._raise = raise_exc
        self.calls = 0

    async def answer(self, question, *, system_prompt=None):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return AnswerResult(
            answer_indices=self._answer_indices,
            confidence=self._confidence,
            reasoning="stub",
            provider="stub",
            from_cache=False,
        )


def _question(*, text: str = "Что такое HTTP?") -> NormalizedQuestion:
    options = [
        Option(index=0, value="1", text="Протокол"),
        Option(index=1, value="2", text="Язык программирования"),
        Option(index=2, value="3", text="Операционная система"),
    ]
    return NormalizedQuestion(
        id="q42:7",
        hash=compute_question_hash(text, "single_choice", options),
        type="single_choice",
        text=text,
        options=options,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="42", cmid="305095", has_images=False
        ),
    )


@pytest_asyncio.fixture
async def ai_client_factory():
    from src.main import create_app

    async def _factory(
        ai: AIProvider,
    ) -> AsyncIterator[AsyncClient]:
        app = create_app()
        app.state.ai_provider = ai
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as c:
                c.headers["X-Backend-Token"] = "test-token"
                yield c

    return _factory


async def _start_session(client: AsyncClient) -> str:
    r = await client.post(
        "/api/session/start",
        json={
            "mode": "assist",
            "cmid": "305095",
            "access_strategy": "extension_native",
        },
    )
    assert r.status_code == 201
    return r.json()["session_id"]


@pytest.mark.asyncio
async def test_answer_returns_result_and_persists_rows(ai_client_factory):
    ai = StubAI(answer_indices=[2], confidence=0.88)
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()

        r = await client.post(
            "/api/question/answer",
            json={
                "session_id": sid,
                "question": q.model_dump(),
                "use_cache": True,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer_indices"] == [2]
        assert body["confidence"] == pytest.approx(0.88)
        assert body["from_cache"] is False
        assert ai.calls == 1

        async with get_session() as db:
            qs = (await db.execute(select(Question))).scalars().all()
            ans = (await db.execute(select(Answer))).scalars().all()
        assert len(qs) == 1
        assert qs[0].hash == q.hash
        assert qs[0].text == q.text
        assert len(ans) == 1
        assert ans[0].answer_indices_json == [2]
        assert ans[0].from_cache is False


@pytest.mark.asyncio
async def test_repeat_question_uses_cache_and_skips_ai(ai_client_factory):
    # High-confidence first answer → cache hit on second call.
    ai = StubAI(answer_indices=[1], confidence=0.95)
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()
        payload = {
            "session_id": sid,
            "question": q.model_dump(),
            "use_cache": True,
        }

        first = await client.post("/api/question/answer", json=payload)
        assert first.status_code == 200
        assert first.json()["from_cache"] is False

        second = await client.post("/api/question/answer", json=payload)
        assert second.status_code == 200
        body = second.json()
        assert body["from_cache"] is True
        assert body["answer_indices"] == [1]
        assert ai.calls == 1


@pytest.mark.asyncio
async def test_low_confidence_answer_is_not_cached(ai_client_factory):
    # Confidence below threshold (0.7) means the next call must re-ask AI.
    ai = StubAI(confidence=0.4)
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()
        payload = {
            "session_id": sid,
            "question": q.model_dump(),
            "use_cache": True,
        }
        await client.post("/api/question/answer", json=payload)
        await client.post("/api/question/answer", json=payload)
        assert ai.calls == 2


@pytest.mark.asyncio
async def test_use_cache_false_always_hits_ai(ai_client_factory):
    ai = StubAI(confidence=0.99)
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()
        payload = {
            "session_id": sid,
            "question": q.model_dump(),
            "use_cache": False,
        }
        await client.post("/api/question/answer", json=payload)
        await client.post("/api/question/answer", json=payload)
        assert ai.calls == 2


@pytest.mark.asyncio
async def test_provider_invalid_response_returns_502(ai_client_factory):
    ai = StubAI(raise_exc=InvalidResponse("bad json"))
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()
        r = await client.post(
            "/api/question/answer",
            json={
                "session_id": sid,
                "question": q.model_dump(),
            },
        )
        assert r.status_code == 502
        assert r.json()["detail"]["code"] == "AI_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_get_cached_returns_404_when_missing(ai_client_factory):
    ai = StubAI()
    async for client in ai_client_factory(ai):
        r = await client.get("/api/question/" + "0" * 64 + "/cached")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_feedback_updates_answer_row(ai_client_factory):
    ai = StubAI(answer_indices=[0], confidence=0.9)
    async for client in ai_client_factory(ai):
        sid = await _start_session(client)
        q = _question()
        await client.post(
            "/api/question/answer",
            json={"session_id": sid, "question": q.model_dump()},
        )

        r = await client.post(
            f"/api/question/{q.hash}/feedback",
            json={"was_correct": True, "session_id": sid},
        )
        assert r.status_code == 204

        async with get_session() as db:
            answers = (await db.execute(select(Answer))).scalars().all()
        assert len(answers) == 1
        assert answers[0].was_correct is True


@pytest.mark.asyncio
async def test_feedback_404_for_unknown_question(ai_client_factory):
    ai = StubAI()
    async for client in ai_client_factory(ai):
        r = await client.post(
            "/api/question/" + "0" * 64 + "/feedback",
            json={"was_correct": False},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_answer_without_ai_provider_returns_503(ai_client_factory):
    # ai_provider=None on app.state — bypassing factory.
    from src.main import create_app

    app = create_app()
    app.state.ai_provider = None
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            c.headers["X-Backend-Token"] = "test-token"
            sid = await _start_session(c)
            r = await c.post(
                "/api/question/answer",
                json={
                    "session_id": sid,
                    "question": _question().model_dump(),
                    "use_cache": False,
                },
            )
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "AI_NOT_CONFIGURED"
