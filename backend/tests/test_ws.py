"""WebSocket protocol tests — auth, state push on connect, command echo."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from src.persistence import Session, get_session


async def _seed_session(sid, mode: str = "assist") -> None:
    async with get_session() as db:
        db.add(
            Session(
                id=sid,
                mode=mode,
                access_strategy="extension_native",
                cmid="305095",
                ai_provider_primary="stub",
                status="running",
            )
        )


@pytest.mark.asyncio
async def test_ws_rejects_invalid_token():
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        sid = uuid4()
        await _seed_session(sid)
        # Spin up a starlette TestClient — its WS adapter is sync.
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{sid}") as ws:
                ws.send_json({"type": "auth", "token": "wrong"})
                with pytest.raises(Exception):
                    ws.receive_json()  # connection closed


@pytest.mark.asyncio
async def test_ws_sends_session_state_after_auth():
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        sid = uuid4()
        await _seed_session(sid, mode="full_auto")
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{sid}") as ws:
                ws.send_json({"type": "auth", "token": "test-token"})
                msg = ws.receive_json()
                assert msg["type"] == "session_state"
                assert msg["session_id"] == str(sid)
                assert msg["mode"] == "full_auto"
                assert msg["status"] == "running"


@pytest.mark.asyncio
async def test_ws_closes_when_session_unknown():
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{uuid4()}") as ws:
                ws.send_json({"type": "auth", "token": "test-token"})
                with pytest.raises(Exception):
                    ws.receive_json()


@pytest.mark.asyncio
async def test_ws_broadcast_reaches_subscribers():
    """An HTTP-triggered broadcast must arrive over a connected WS."""
    from src.api.ws import broadcast
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        sid = uuid4()
        await _seed_session(sid)
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{sid}") as ws:
                ws.send_json({"type": "auth", "token": "test-token"})
                ws.receive_json()  # session_state

                await broadcast(sid, {"type": "answer_suggested", "question_id": "q1"})
                msg = ws.receive_json()
                assert msg["type"] == "answer_suggested"
                assert msg["question_id"] == "q1"


@pytest.mark.asyncio
async def test_ws_command_echoes_log_event():
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        sid = uuid4()
        await _seed_session(sid)
        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/{sid}") as ws:
                ws.send_json({"type": "auth", "token": "test-token"})
                ws.receive_json()  # session_state

                ws.send_json({"type": "confirm_answer", "question_id": "q1"})
                msg = ws.receive_json()
                assert msg["type"] == "log"
                assert "confirm_answer" in msg["msg"]
