"""Unit tests for GeminiProvider with the google-genai SDK mocked at the
client boundary. No network calls happen here; tests verify parsing,
error classification, and Pydantic validation paths.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from src.ai.base import (
    InvalidResponse,
    ProviderTimeout,
    ProviderUnavailable,
    QuotaExceeded,
)
from src.ai.gemini import GeminiProvider
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _question(*, q_type: str = "single_choice", n_options: int = 3) -> NormalizedQuestion:
    options = [
        Option(index=i, value=str(i + 1), text=f"opt{i}") for i in range(n_options)
    ]
    return NormalizedQuestion(
        id="q1:1",
        hash="0" * 64,
        type=q_type,
        text="Test question?",
        options=options,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="1", cmid="1", has_images=False
        ),
    )


def _make_provider(client: Any) -> GeminiProvider:
    """Construct a GeminiProvider and swap in a fake client.

    We pass `api_key="x"` so the __init__ check passes; the real
    `genai.Client` is constructed but never used because we overwrite
    `_client` before any call.
    """
    provider = GeminiProvider(
        api_key="x", model="gemini-2.0-flash", timeout_s=1.0
    )
    provider._client = client
    return provider


def _fake_client(
    *, text: str | None = None, raise_exc: Exception | None = None
) -> Any:
    """Build a stand-in for `genai.Client` exposing only `aio.models.generate_content`."""

    async def generate_content(**_kwargs: Any) -> Any:
        if raise_exc is not None:
            raise raise_exc
        return SimpleNamespace(text=text, candidates=None)

    return SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )


def test_gemini_constructor_requires_api_key():
    with pytest.raises(ValueError):
        GeminiProvider(api_key="", model="x")


@pytest.mark.asyncio
async def test_gemini_returns_parsed_answer():
    provider = _make_provider(
        _fake_client(
            text='{"answer_indices": [1], "confidence": 0.91, "reasoning": "because"}'
        )
    )

    result = await provider.answer(_question())

    assert result.answer_indices == [1]
    assert result.confidence == pytest.approx(0.91)
    assert result.reasoning == "because"
    assert result.provider == "gemini-2.0-flash"
    assert result.from_cache is False
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_gemini_429_classified_as_quota_exceeded():
    provider = _make_provider(
        _fake_client(raise_exc=RuntimeError("HTTP 429 too many requests"))
    )
    with pytest.raises(QuotaExceeded):
        await provider.answer(_question())


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["quota exceeded", "rate limit", "resource exhausted"])
async def test_gemini_quota_keywords_classified_as_quota_exceeded(text):
    provider = _make_provider(_fake_client(raise_exc=RuntimeError(text)))
    with pytest.raises(QuotaExceeded):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_other_errors_classified_as_unavailable():
    provider = _make_provider(_fake_client(raise_exc=RuntimeError("network broken")))
    with pytest.raises(ProviderUnavailable):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_timeout_raises_provider_timeout():
    provider = _make_provider(_fake_client(raise_exc=asyncio.TimeoutError()))
    with pytest.raises(ProviderTimeout):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_slow_response_hits_wait_for_timeout():
    """Even if the SDK never raises TimeoutError itself, asyncio.wait_for
    should — we configure timeout_s=0.05 and make generate_content sleep
    longer than that.
    """

    async def slow_generate(**_kwargs: Any) -> Any:
        await asyncio.sleep(0.2)
        return SimpleNamespace(text='{"answer_indices":[0],"confidence":0.9}')

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=slow_generate))
    )
    provider = GeminiProvider(api_key="x", model="x", timeout_s=0.05)
    provider._client = client

    with pytest.raises(ProviderTimeout):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_empty_text_raises_invalid_response():
    provider = _make_provider(_fake_client(text=""))
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_malformed_json_raises_invalid_response():
    provider = _make_provider(_fake_client(text="not json at all"))
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_index_out_of_range_raises_invalid_response():
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [99], "confidence": 0.9}')
    )
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_negative_index_raises_invalid_response():
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [-1], "confidence": 0.9}')
    )
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_single_choice_trims_extra_indices():
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [1, 2], "confidence": 0.9}')
    )
    result = await provider.answer(_question(q_type="single_choice"))
    assert result.answer_indices == [1]
    # Confidence is penalized (multiplied by 0.7) because the model returned
    # multiple indices on a single-choice question.
    assert result.confidence == pytest.approx(0.9 * 0.7)


@pytest.mark.asyncio
async def test_gemini_multiple_choice_preserves_all_indices():
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [0, 2], "confidence": 0.95}')
    )
    result = await provider.answer(_question(q_type="multiple_choice"))
    assert result.answer_indices == [0, 2]
    assert result.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_gemini_empty_answer_indices_raises_invalid_response():
    """RawAIResponse requires min_length=1 → Pydantic rejects empty list."""
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [], "confidence": 0.9}')
    )
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_gemini_confidence_out_of_range_raises_invalid_response():
    provider = _make_provider(
        _fake_client(text='{"answer_indices": [0], "confidence": 1.5}')
    )
    with pytest.raises(InvalidResponse):
        await provider.answer(_question())
