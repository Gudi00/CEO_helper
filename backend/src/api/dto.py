"""HTTP request/response DTOs matching docs/specs/api-contract.yaml."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.ai.base import AnswerResult
from src.moodle.types import NormalizedQuestion

ExecutionMode = Literal["assist", "full_auto", "step_by_step"]
AccessStrategy = Literal["extension_native", "cdp", "manual_login", "cookie_export"]
SessionStatus = Literal["running", "completed", "aborted", "failed"]


class StartSessionRequest(BaseModel):
    mode: ExecutionMode
    cmid: str
    access_strategy: AccessStrategy = "extension_native"
    ai_provider_override: str | None = None


class StartSessionResponse(BaseModel):
    session_id: UUID
    ws_url: str


class SessionStateDTO(BaseModel):
    session_id: UUID
    mode: ExecutionMode
    status: SessionStatus
    cmid: str
    attempt_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    score: int | None = None
    max_score: int | None = None


class AnswerRequest(BaseModel):
    session_id: UUID
    question: NormalizedQuestion
    use_cache: bool = True


class FeedbackRequest(BaseModel):
    was_correct: bool
    session_id: UUID | None = None


class AttemptSummary(BaseModel):
    session_id: UUID
    cmid: str
    mode: ExecutionMode
    score: int | None
    max_score: int | None
    started_at: datetime
    duration_s: int | None
    status: SessionStatus


class HistoryAnswer(BaseModel):
    question_text: str
    options_text: list[str]
    ai_answer_indices: list[int]
    confidence: float
    reasoning: str | None
    provider: str
    from_cache: bool
    was_correct: bool | None
    created_at: datetime


class AttemptDetail(AttemptSummary):
    answers: list[HistoryAnswer] = Field(default_factory=list)


class StartEngineRequest(BaseModel):
    session_id: UUID
    access_strategy: Literal["cdp", "manual_login", "cookie_export"] = "cdp"
    cdp_port: int = 9222


class StopEngineRequest(BaseModel):
    session_id: UUID


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    ai_provider_primary: str
    version: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None


__all__ = [
    "AccessStrategy",
    "AnswerRequest",
    "AnswerResult",
    "AttemptDetail",
    "AttemptSummary",
    "ErrorBody",
    "ExecutionMode",
    "FeedbackRequest",
    "HealthResponse",
    "HistoryAnswer",
    "SessionStateDTO",
    "SessionStatus",
    "StartEngineRequest",
    "StartSessionRequest",
    "StartSessionResponse",
    "StopEngineRequest",
]
