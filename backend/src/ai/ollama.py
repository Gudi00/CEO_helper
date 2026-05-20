from __future__ import annotations

import asyncio
import json
import re
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
from src.ai.prompts import build_system_prompt, render_user_prompt
from src.moodle.types import NormalizedQuestion

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        host: str,
        model: str,
        timeout_s: float = 30.0,
        think: bool = False,
        num_predict: int = 1024,
        num_gpu: int = 99,
    ) -> None:
        self._client = AsyncClient(host=host)
        self._model = model
        self._timeout_s = timeout_s
        self._think = think
        self._num_predict = num_predict
        self._num_gpu = num_gpu

    async def answer(
        self, question: NormalizedQuestion, *, system_prompt: str | None = None
    ) -> AnswerResult:
        prompt = render_user_prompt(question)
        started = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": self._model,
            "options": {
                "temperature": 0.1,
                "num_predict": self._num_predict,
                "num_gpu": self._num_gpu,
            },
            "messages": [
                {"role": "system", "content": build_system_prompt(system_prompt)},
                {"role": "user", "content": prompt},
            ],
        }
        if not self._think:
            kwargs["format"] = "json"

        try:
            response: Any = await asyncio.wait_for(
                self._client.chat(**kwargs),
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
        # Strip <think>...</think> blocks emitted by reasoning models (e.g. deepseek-r1)
        cleaned = _THINK_RE.sub("", raw_text).strip()
        # If no JSON object found in cleaned text, fall back to raw
        m = _JSON_OBJ_RE.search(cleaned)
        json_text = m.group(0) if m else cleaned

        try:
            data = json.loads(json_text)
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
