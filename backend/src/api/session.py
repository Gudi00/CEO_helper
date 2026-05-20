from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from src.api.dto import (
    SessionStateDTO,
    StartSessionRequest,
    StartSessionResponse,
)
from src.auth import verify_token
from src.config import get_settings
from src.persistence import Session, get_session

router = APIRouter(prefix="/session", tags=["session"], dependencies=[Depends(verify_token)])


@router.post("/start", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(req: StartSessionRequest) -> StartSessionResponse:
    settings = get_settings()
    async with get_session() as db:
        session = Session(
            mode=req.mode,
            access_strategy=req.access_strategy,
            cmid=req.cmid,
            ai_provider_primary=req.ai_provider_override or settings.gemini_model,
            status="running",
        )
        db.add(session)
        await db.flush()
        ws_url = f"ws://{settings.backend_host}:{settings.backend_port}/ws/{session.id}"
        return StartSessionResponse(session_id=session.id, ws_url=ws_url)


@router.get("/{session_id}", response_model=SessionStateDTO)
async def get_session_state(session_id: UUID) -> SessionStateDTO:
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "session"})
        return _to_dto(session)


@router.post("/{session_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_session(session_id: UUID) -> None:
    async with get_session() as db:
        session = await db.get(Session, session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "session"})
        if session.status == "running":
            session.status = "aborted"


def _to_dto(session: Session) -> SessionStateDTO:
    return SessionStateDTO(
        session_id=session.id,
        mode=session.mode,  # type: ignore[arg-type]
        status=session.status,  # type: ignore[arg-type]
        cmid=session.cmid,
        attempt_id=session.attempt_id,
        started_at=session.started_at,
        finished_at=session.finished_at,
        score=session.score,
        max_score=session.max_score,
    )
