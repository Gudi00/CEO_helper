from __future__ import annotations

import asyncio
import base64
import json
import time

from google import genai
from google.genai import types
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


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(
        self, *, api_key: str, model: str, timeout_s: float = 10.0
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiProvider")
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._timeout_s = timeout_s
        self._config = types.GenerateContentConfig(
            system_instruction=build_system_prompt(None),
            temperature=0.1,
            max_output_tokens=1024,
            top_p=0.95,
            response_mime_type="application/json",
        )

    async def answer(
        self, question: NormalizedQuestion, *, system_prompt: str | None = None
    ) -> AnswerResult:
        prompt = render_user_prompt(question)
        started = time.perf_counter()
        config = self._config
        if system_prompt:
            config = types.GenerateContentConfig(
                system_instruction=build_system_prompt(system_prompt),
                temperature=0.1,
                max_output_tokens=1024,
                top_p=0.95,
                response_mime_type="application/json",
            )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=_contents(prompt, question),
                    config=config,
                ),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
            msg = f"gemini exceeded {self._timeout_s}s"
            raise ProviderTimeout(msg) from exc
        except Exception as exc:
            raise _classify(exc) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        raw_text = (response.text or "").strip()
        if not raw_text:
            raise InvalidResponse("Gemini returned empty response")

        parsed = _parse_and_validate(raw_text, question)
        return AnswerResult(
            answer_indices=parsed.answer_indices,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            provider=self._model_name,
            from_cache=False,
            latency_ms=latency_ms,
        )


def _contents(prompt: str, question: NormalizedQuestion) -> str | list[types.Part]:
    if not question.images:
        return prompt
    return [
        *(
            types.Part.from_bytes(data=base64.b64decode(img.data), mime_type=img.mime)
            for img in question.images
        ),
        types.Part.from_text(text=prompt),
    ]


def _classify(exc: Exception) -> Exception:
    msg = str(exc).lower()
    if "429" in msg or "quota" in msg or "rate" in msg or "exhausted" in msg:
        return QuotaExceeded(str(exc))
    return ProviderUnavailable(str(exc))


def _parse_and_validate(
    raw_text: str, question: NormalizedQuestion
) -> RawAIResponse:
    try:
        data = json.loads(raw_text)
        parsed = RawAIResponse(**data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise InvalidResponse(f"Bad JSON from Gemini: {raw_text[:120]!r}") from exc

    max_index = len(question.options) - 1
    if any(i < 0 or i > max_index for i in parsed.answer_indices):
        msg = f"index out of range: {parsed.answer_indices} (max {max_index})"
        raise InvalidResponse(msg)

    if question.type == "single_choice" and len(parsed.answer_indices) != 1:
        parsed = RawAIResponse(
            answer_indices=parsed.answer_indices[:1],
            confidence=parsed.confidence * 0.7,
            reasoning=parsed.reasoning,
        )

    return parsed
