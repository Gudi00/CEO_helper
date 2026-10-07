from __future__ import annotations

import logging
from collections.abc import Sequence

from src.ai.base import (
    AIProvider,
    AIProviderError,
    AnswerResult,
    InvalidResponse,
    ProviderTimeout,
    ProviderUnavailable,
    QuotaExceeded,
)
from src.moodle.types import NormalizedQuestion

logger = logging.getLogger(__name__)

_RECOVERABLE = (QuotaExceeded, ProviderTimeout, ProviderUnavailable, InvalidResponse)


class CascadeProvider:
    """Tries providers in order, falling back on any provider failure.

    An InvalidResponse also falls through: a model that returned unusable
    JSON says nothing about whether the next model can answer.
    """

    name = "cascade"

    def __init__(self, providers: Sequence[AIProvider]) -> None:
        if not providers:
            raise ValueError("CascadeProvider requires at least one provider")
        self._providers = list(providers)

    async def answer(
        self, question: NormalizedQuestion, *, system_prompt: str | None = None
    ) -> AnswerResult:
        last_err: AIProviderError | None = None
        for provider in self._providers:
            try:
                return await provider.answer(question, system_prompt=system_prompt)
            except _RECOVERABLE as exc:
                logger.warning(
                    "provider %s failed with %s, falling back",
                    provider.name,
                    type(exc).__name__,
                )
                last_err = exc
                continue
        assert last_err is not None
        raise last_err
