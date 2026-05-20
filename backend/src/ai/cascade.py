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

_RECOVERABLE = (QuotaExceeded, ProviderTimeout, ProviderUnavailable)


class CascadeProvider:
    """Tries providers in order. Falls back on recoverable errors only.

    See ADR 0003: Gemini → Ollama. InvalidResponse is NOT recoverable —
    it likely means the question is malformed, not the provider.
    """

    name = "cascade"

    def __init__(self, providers: Sequence[AIProvider]) -> None:
        if not providers:
            raise ValueError("CascadeProvider requires at least one provider")
        self._providers = list(providers)

    async def answer(self, question: NormalizedQuestion) -> AnswerResult:
        last_err: AIProviderError | None = None
        for provider in self._providers:
            try:
                return await provider.answer(question)
            except _RECOVERABLE as exc:
                logger.warning(
                    "provider %s failed with %s, falling back",
                    provider.name,
                    type(exc).__name__,
                )
                last_err = exc
                continue
            except InvalidResponse:
                raise
        assert last_err is not None
        raise last_err
