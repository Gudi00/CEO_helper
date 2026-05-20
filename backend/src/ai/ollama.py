from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from ollama import AsyncClient
from pydantic import ValidationError

from src.ai.base import (
    AIProvider,
    AnswerResult,
    InvalidResponse,
    ProviderTimeout,
    ProviderUnavailable,
    RawAIResponse,
)
from src.ai.prompts import SYSTEM_PROMPT, render_user_prompt
from src.moodle.types import NormalizedQuestion


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, *, host: str, model: str, timeout_s: float = 30.0) -> None:
        self._client = AsyncClient(host=host)
        self._model = model
        self._timeout_s = timeout_s

    async def answer(self, question: NormalizedQuestion) -> AnswerResult:
        prompt = render_user_prompt(question)
        started = time.perf_counter()
        try:
            response: Any = await asyncio.wait_for(
                self._client.chat(
                    model=self._model,
                    format="json",
                    options={"temperature": 0.1, "num_predict": 200},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                ),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
            raise ProviderTimeout(f"ollama exceeded {self._timeout_s}s") from exc
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = response.get("message", {}).get("content", "") if isinstance(response, dict) else ""
        if not content:
            content = getattr(response.message, "content", "") if hasattr(response, "message") else ""
        if not content:
            raise InvalidResponse("Ollama returned empty content")

        parsed = self._parse_and_validate(content, question)
        return AnswerResult(
            answer_indices=parsed.answer_indices,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            provider=self._model,
            from_cache=False,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _parse_and_validate(
        raw_text: str, question: NormalizedQuestion
    ) -> RawAIResponse:
        try:
            data = json.loads(raw_text)
            parsed = RawAIResponse(**data)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise InvalidResponse(f"Bad JSON from Ollama: {raw_text[:120]!r}") from exc

        max_index = len(question.options) - 1
        if any(i < 0 or i > max_index for i in parsed.answer_indices):
            raise InvalidResponse(
                f"index out of range: {parsed.answer_indices} (max {max_index})"
            )

        if question.type == "single_choice" and len(parsed.answer_indices) != 1:
            parsed = RawAIResponse(
                answer_indices=parsed.answer_indices[:1],
                confidence=parsed.confidence * 0.7,
                reasoning=parsed.reasoning,
            )
        return parsed
