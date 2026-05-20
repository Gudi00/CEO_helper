"""WebSocket handler — server→client events + client→server commands.

See docs/specs/ws-protocol.md.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.config import get_settings
from src.persistence import Session, get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

_subscribers: dict[UUID, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


async def broadcast(session_id: UUID, message: dict) -> None:
    async with _lock:
        listeners = list(_subscribers.get(session_id, ()))
    for ws in listeners:
        if ws.client_state == WebSocketState.CONNECTED:
            with suppress(Exception):
                await ws.send_json(message)


@router.websocket("/ws/{session_id}")
async def session_ws(websocket: WebSocket, session_id: UUID) -> None:
    await websocket.accept()

    auth = await websocket.receive_json()
    expected_token = get_settings().ensure_token()
    if auth.get("type") != "auth" or auth.get("token") != expected_token:
        await websocket.close(code=4401, reason="invalid token")
        return

    async with get_session() as db:
        session = await db.get(Session, session_id)
        if session is None:
            await websocket.close(code=4404, reason="session not found")
            return
        state_msg = {
            "type": "session_state",
            "session_id": str(session.id),
            "mode": session.mode,
            "status": session.status,
            "current_page": 0,
            "questions_answered": 0,
        }

    # Register the subscriber BEFORE the first send so a client that
    # immediately triggers a broadcast cannot race past the registration.
    async with _lock:
        _subscribers[session_id].add(websocket)
    await websocket.send_json(state_msg)

    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        async for command in _read_loop(websocket):
            await _handle_command(session_id, command)
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat.cancel()
        async with _lock:
            _subscribers[session_id].discard(websocket)


async def _read_loop(ws: WebSocket) -> AsyncIterator[dict]:
    while True:
        msg = await ws.receive_json()
        yield msg


_KNOWN_COMMANDS = frozenset(
    {"confirm_answer", "reject_answer", "pause", "resume", "abort"}
)


async def _handle_command(session_id: UUID, cmd: dict) -> None:
    cmd_type = cmd.get("type")
    if cmd_type in _KNOWN_COMMANDS:
        # MVP: forward as a log event so the UI can see commands flowing;
        # full state-machine integration is Phase 1 work.
        await broadcast(
            session_id,
            {
                "type": "log",
                "level": "info",
                "msg": f"received {cmd_type}",
            },
        )
    else:
        logger.warning(
            "unknown ws command %s for session %s", cmd_type, session_id
        )


async def _heartbeat(ws: WebSocket) -> None:
    try:
        while ws.client_state == WebSocketState.CONNECTED:
            await asyncio.sleep(30)
            with suppress(Exception):
                await ws.send_json({"type": "ping"})
    except asyncio.CancelledError:
        return
