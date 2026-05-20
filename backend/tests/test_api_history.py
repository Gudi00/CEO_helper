"""Tests for /api/history (list + detail).

Seeds the DB directly (bypassing the assist endpoint) so the history
endpoints can be exercised in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.persistence import Answer, Question, Session, get_session

_seq = 0


def _next_hash() -> str:
    global _seq
    _seq += 1
    return f"{_seq:064x}"


async def _seed_attempt(
    *,
    cmid: str = "305095",
    mode: str = "assist",
    status: str = "completed",
    score: int = 14,
    max_score: int = 20,
    started_at: datetime | None = None,
):
    sid = uuid4()
    q_hash = _next_hash()
    started = started_at or datetime.now(UTC)
    finished = started + timedelta(seconds=420)

    async with get_session() as db:
        db.add(
            Session(
                id=sid,
                mode=mode,
                access_strategy="cdp",
                cmid=cmid,
                ai_provider_primary="stub",
                status=status,
                started_at=started,
                finished_at=finished,
                score=score,
                max_score=max_score,
            )
        )
        db.add(
            Question(
                hash=q_hash,
                text="Test question?",
                options_json=[
                    {"index": 0, "value": "1", "text": "A"},
                    {"index": 1, "value": "2", "text": "B"},
                ],
                q_type="single_choice",
            )
        )
        db.add(
            Answer(
                session_id=sid,
                question_hash=q_hash,
                answer_indices_json=[1],
                confidence=0.9,
                reasoning="stub",
                provider="stub",
                from_cache=False,
            )
        )
    return sid


@pytest.mark.asyncio
async def test_history_list_returns_seeded_attempts(client):
    sid1 = await _seed_attempt(cmid="111")
    sid2 = await _seed_attempt(cmid="222")

    r = await client.get("/api/history")
    assert r.status_code == 200
    body = r.json()
    assert {row["session_id"] for row in body} == {str(sid1), str(sid2)}
    assert all(row["score"] == 14 and row["max_score"] == 20 for row in body)
    assert all(row["duration_s"] == 420 for row in body)


@pytest.mark.asyncio
async def test_history_list_filtered_by_cmid(client):
    sid1 = await _seed_attempt(cmid="111")
    await _seed_attempt(cmid="222")

    r = await client.get("/api/history", params={"cmid": "111"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["session_id"] == str(sid1)


@pytest.mark.asyncio
async def test_history_list_respects_limit(client):
    for _ in range(3):
        await _seed_attempt()

    r = await client.get("/api/history", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_history_list_orders_newest_first(client):
    older = await _seed_attempt(
        started_at=datetime.now(UTC) - timedelta(days=2)
    )
    newer = await _seed_attempt(started_at=datetime.now(UTC))

    body = (await client.get("/api/history")).json()
    assert [row["session_id"] for row in body] == [str(newer), str(older)]


@pytest.mark.asyncio
async def test_history_detail_includes_answers(client):
    sid = await _seed_attempt()

    r = await client.get(f"/api/history/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == str(sid)
    assert body["score"] == 14
    assert len(body["answers"]) == 1
    a = body["answers"][0]
    assert a["question_text"] == "Test question?"
    assert a["options_text"] == ["A", "B"]
    assert a["ai_answer_indices"] == [1]
    assert a["provider"] == "stub"


@pytest.mark.asyncio
async def test_history_detail_404_for_unknown_id(client):
    r = await client.get(f"/api/history/{uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_history_endpoint_requires_token(client):
    del client.headers["X-Backend-Token"]
    r = await client.get("/api/history")
    assert r.status_code == 401
