from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from src.api.dto import AttemptDetail, AttemptSummary, HistoryAnswer
from src.auth import verify_token
from src.persistence import Question, Session, get_session

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(verify_token)])


@router.get("", response_model=list[AttemptSummary])
async def list_history(
    limit: int = Query(50, ge=1, le=500),
    cmid: str | None = None,
) -> list[AttemptSummary]:
    async with get_session() as db:
        stmt = select(Session).order_by(desc(Session.started_at)).limit(limit)
        if cmid is not None:
            stmt = stmt.where(Session.cmid == cmid)
        rows = (await db.execute(stmt)).scalars().all()
        return [_summary(s) for s in rows]


@router.get("/{attempt_id}", response_model=AttemptDetail)
async def get_history_item(attempt_id: UUID) -> AttemptDetail:
    async with get_session() as db:
        stmt = (
            select(Session)
            .where(Session.id == attempt_id)
            .options(selectinload(Session.answers))
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "attempt"})

        answers: list[HistoryAnswer] = []
        for a in sorted(session.answers, key=lambda x: x.created_at):
            q = await db.get(Question, a.question_hash)
            answers.append(
                HistoryAnswer(
                    question_text=q.text if q else "",
                    options_text=[o["text"] for o in (q.options_json if q else [])],
                    ai_answer_indices=a.answer_indices_json,
                    confidence=a.confidence,
                    reasoning=a.reasoning,
                    provider=a.provider,
                    from_cache=a.from_cache,
                    was_correct=a.was_correct,
                    created_at=a.created_at,
                )
            )

        summary = _summary(session)
        return AttemptDetail(**summary.model_dump(), answers=answers)


def _summary(session: Session) -> AttemptSummary:
    duration: int | None = None
    if session.finished_at is not None:
        duration = int((session.finished_at - session.started_at).total_seconds())
    return AttemptSummary(
        session_id=session.id,
        cmid=session.cmid,
        mode=session.mode,  # type: ignore[arg-type]
        score=session.score,
        max_score=session.max_score,
        started_at=session.started_at,
        duration_s=duration,
        status=session.status,  # type: ignore[arg-type]
    )
