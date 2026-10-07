from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from src.ai.base import (
    AIProvider,
    AnswerResult,
    InvalidResponse,
    ProviderTimeout,
    ProviderUnavailable,
    QuotaExceeded,
    RawAIResponse,
)
from src.ai.prompts import build_system_prompt, render_user_prompt
from src.moodle.types import NormalizedQuestion

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


class OpenAICompatProvider(AIProvider):
    """Chat-completions client for any OpenAI-compatible endpoint
    (OpenRouter, DeepSeek, Groq, LM Studio, llama.cpp server, vLLM).
    """

    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 60.0,
        max_tokens: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not model:
            raise ValueError("base_url and model are required for OpenAICompatProvider")
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout_s = timeout_s
        self._max_tokens = max_tokens
        self._transport = transport

    async def answer(
        self, question: NormalizedQuestion, *, system_prompt: str | None = None
    ) -> AnswerResult:
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.1,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": build_system_prompt(system_prompt)},
                {"role": "user", "content": _user_content(question)},
            ],
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(self._url, json=body, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"{self._model} exceeded {self._timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc

        if response.status_code == 429:
            raise QuotaExceeded(f"{self._model}: HTTP 429")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"{self._model}: HTTP {response.status_code}")

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            content = response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise InvalidResponse(f"{self._model}: unexpected response shape") from exc

        parsed = _parse_and_validate(content, question)
        return AnswerResult(
            answer_indices=parsed.answer_indices,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            provider=self._model,
            from_cache=False,
            latency_ms=latency_ms,
        )


def _user_content(question: NormalizedQuestion) -> str | list[dict[str, Any]]:
    prompt = render_user_prompt(question)
    if not question.images:
        return prompt
    return [
        {"type": "text", "text": prompt},
        *(
            {"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{img.data}"}}
            for img in question.images
        ),
    ]


def _parse_and_validate(raw_text: str, question: NormalizedQuestion) -> RawAIResponse:
    # Reasoning models may wrap output in <think> or markdown fences.
    cleaned = _THINK_RE.sub("", raw_text).strip()
    m = _JSON_OBJ_RE.search(cleaned)
    try:
        parsed = RawAIResponse(**json.loads(m.group(0) if m else cleaned))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise InvalidResponse(f"Bad JSON from model: {raw_text[:120]!r}") from exc

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
