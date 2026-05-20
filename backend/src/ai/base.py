from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.moodle.types import NormalizedQuestion


class RawAIResponse(BaseModel):
    """Raw JSON the model returns. Validated before being elevated to AnswerResult."""

    answer_indices: list[int] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None


class AnswerResult(BaseModel):
    answer_indices: list[int]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
    provider: str
    from_cache: bool = False
    latency_ms: int | None = None


class AIProviderError(RuntimeError):
    """Base class for AI provider failures.

    Subclasses signal the cascade what to do:
      - QuotaExceeded / Timeout / Unavailable → try next provider
      - InvalidResponse → bubble up, do not retry
    """


class QuotaExceeded(AIProviderError):
    pass


class ProviderTimeout(AIProviderError):
    pass


class ProviderUnavailable(AIProviderError):
    pass


class InvalidResponse(AIProviderError):
    pass


@runtime_checkable
class AIProvider(Protocol):
    name: str

    async def answer(
        self, question: NormalizedQuestion, *, system_prompt: str | None = None
    ) -> AnswerResult: ...
