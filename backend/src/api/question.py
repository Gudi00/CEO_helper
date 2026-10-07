from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select

from src.ai.base import (
    AIProvider,
    AIProviderError,
    AnswerResult,
    InvalidResponse,
)
from src.api.dto import AnswerRequest, FeedbackRequest
from src.auth import verify_token
from src.persistence import Answer, Question, Session, get_session

router = APIRouter(
    prefix="/question",
    tags=["question"],
    dependencies=[Depends(verify_token)],
)

CACHE_TTL = timedelta(days=30)
CACHE_MIN_CONFIDENCE = 0.7

logger = logging.getLogger(__name__)

# One lock per question hash: identical questions arriving together (two
# tabs, a re-rendered page) share a single model call and a single insert.
_hash_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _get_provider(request: Request, preference: str = "accurate") -> AIProvider:
    providers: dict[str, AIProvider] = getattr(request.app.state, "ai_providers", {})
    provider = providers.get(preference) or providers.get("fast") or request.app.state.ai_provider
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AI_NOT_CONFIGURED",
                "message": "Set GEMINI_API_KEY or enable OLLAMA",
            },
        )
    return provider  # type: ignore[no-any-return]


@router.post("/answer", response_model=AnswerResult)
async def answer_question(
    req: AnswerRequest, request: Request
) -> AnswerResult:
    async with _hash_locks[req.question.hash]:
        # The hash covers text only, so two questions that differ just by
        # their picture share it — never serve or reuse a cached answer here.
        if req.use_cache and not req.question.metadata.has_images:
            cached = await _get_recent_cached_answer(req.question.hash)
            if cached is not None:
                return cached

        provider = _get_provider(request, req.model_preference)
        try:
            result = await provider.answer(req.question, system_prompt=req.system_prompt)
        except InvalidResponse as exc:
            # Raw model output stays in the log; the client gets a code only.
            logger.warning("invalid AI response for %s: %s", req.question.hash[:12], exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "AI_INVALID_RESPONSE",
                    "message": "Model returned an unusable answer",
                },
            ) from exc
        except AIProviderError as exc:
            logger.warning("AI provider failed for %s: %s", req.question.hash[:12], exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "AI_PROVIDER_FAILED",
                    "message": type(exc).__name__,
                },
            ) from exc

        await _persist_answer(req, result)
        return result


@router.get("/{question_hash}/cached", response_model=AnswerResult)
async def get_cached(question_hash: str) -> AnswerResult:
    cached = await _get_recent_cached_answer(question_hash)
    if cached is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_CACHED", "message": question_hash},
        )
    return cached


@router.post(
    "/{question_hash}/feedback", status_code=status.HTTP_204_NO_CONTENT
)
async def submit_feedback(
    question_hash: str, body: FeedbackRequest
) -> None:
    async with get_session() as db:
        stmt = (
            select(Answer)
            .where(Answer.question_hash == question_hash)
            .order_by(desc(Answer.created_at))
            .limit(1)
        )
        if body.session_id is not None:
            stmt = stmt.where(Answer.session_id == body.session_id)
        result = await db.execute(stmt)
        answer = result.scalar_one_or_none()
        if answer is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "answer"},
            )
        answer.was_correct = body.was_correct


async def _get_recent_cached_answer(
    question_hash: str,
) -> AnswerResult | None:
    cutoff = datetime.now(UTC) - CACHE_TTL
    async with get_session() as db:
        stmt = (
            select(Answer)
            .where(
                Answer.question_hash == question_hash,
                Answer.confidence >= CACHE_MIN_CONFIDENCE,
                Answer.created_at >= cutoff,
            )
            .order_by(desc(Answer.created_at))
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return AnswerResult(
            answer_indices=row.answer_indices_json,
            confidence=row.confidence,
            reasoning=row.reasoning,
            provider=row.provider,
            from_cache=True,
        )


async def _persist_answer(req: AnswerRequest, result: AnswerResult) -> None:
    q = req.question
    async with get_session() as db:
        existing = await db.get(Question, q.hash)
        if existing is None:
            db.add(
                Question(
                    hash=q.hash,
                    text=q.text,
                    options_json=[o.model_dump() for o in q.options],
                    q_type=q.type,
                )
            )
        else:
            existing.times_seen += 1

        session = await db.get(Session, req.session_id)
        if session is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "session"},
            )
        session.attempt_id = q.metadata.attempt_id

        db.add(
            Answer(
                session_id=req.session_id,
                question_hash=q.hash,
                answer_indices_json=result.answer_indices,
                confidence=result.confidence,
                reasoning=result.reasoning,
                provider=result.provider,
                from_cache=False,
            )
        )
