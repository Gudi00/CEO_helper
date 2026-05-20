from __future__ import annotations

import pytest

from src.ai.base import (
    AIProvider,
    AnswerResult,
    InvalidResponse,
    ProviderTimeout,
    ProviderUnavailable,
    QuotaExceeded,
)
from src.ai.cascade import CascadeProvider
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _q() -> NormalizedQuestion:
    options = [Option(index=i, value=str(i + 1), text=f"opt{i}") for i in range(2)]
    return NormalizedQuestion(
        id="q1:1",
        hash="0" * 64,
        type="single_choice",
        text="x?",
        options=options,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="1", cmid="1", has_images=False
        ),
    )


class Recording(AIProvider):
    def __init__(self, name: str, *, raise_exc: Exception | None = None) -> None:
        self.name = name
        self._raise = raise_exc
        self.calls = 0

    async def answer(self, question, *, system_prompt=None):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return AnswerResult(
            answer_indices=[0],
            confidence=0.9,
            reasoning=f"by {self.name}",
            provider=self.name,
            from_cache=False,
        )


def test_cascade_requires_at_least_one_provider():
    with pytest.raises(ValueError):
        CascadeProvider([])


@pytest.mark.asyncio
async def test_cascade_returns_first_provider_success():
    primary = Recording("primary")
    fallback = Recording("fallback")
    cascade = CascadeProvider([primary, fallback])

    result = await cascade.answer(_q())

    assert result.provider == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.parametrize(
    "exc_type",
    [QuotaExceeded, ProviderTimeout, ProviderUnavailable],
)
@pytest.mark.asyncio
async def test_cascade_falls_back_on_recoverable_errors(exc_type):
    primary = Recording("primary", raise_exc=exc_type("boom"))
    fallback = Recording("fallback")
    cascade = CascadeProvider([primary, fallback])

    result = await cascade.answer(_q())

    assert result.provider == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_cascade_propagates_invalid_response_without_fallback():
    primary = Recording("primary", raise_exc=InvalidResponse("bad json"))
    fallback = Recording("fallback")
    cascade = CascadeProvider([primary, fallback])

    with pytest.raises(InvalidResponse):
        await cascade.answer(_q())

    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_cascade_raises_last_error_when_all_fail():
    primary = Recording("primary", raise_exc=QuotaExceeded("out"))
    fallback = Recording("fallback", raise_exc=ProviderTimeout("slow"))
    cascade = CascadeProvider([primary, fallback])

    with pytest.raises(ProviderTimeout):
        await cascade.answer(_q())

    assert primary.calls == 1
    assert fallback.calls == 1
