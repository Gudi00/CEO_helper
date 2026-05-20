"""Unit tests for OllamaProvider with the `ollama` SDK mocked at the
client boundary.

Ollama's Python SDK has two response shapes (dict or object with .message);
the provider supports both. Each shape is exercised below.
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
)
from src.ai.ollama import OllamaProvider
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _question(
    *, q_type: str = "single_choice", n_options: int = 3
) -> NormalizedQuestion:
    options = [
        Option(index=i, value=str(i + 1), text=f"opt{i}")
        for i in range(n_options)
    ]
    return NormalizedQuestion(
        id="q1:1",
        hash="0" * 64,
        type=q_type,
        text="Test?",
        options=options,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="1", cmid="1", has_images=False
        ),
    )


def _provider() -> OllamaProvider:
    return OllamaProvider(
        host="http://localhost:11434", model="gemma3:4b", timeout_s=1.0
    )


def _dict_response(content: str) -> dict[str, Any]:
    return {"message": {"role": "assistant", "content": content}}


def _object_response(content: str) -> Any:
    return SimpleNamespace(
        message=SimpleNamespace(role="assistant", content=content)
    )


def _install_chat(provider: OllamaProvider, fn) -> None:
    """Replace `provider._client.chat` with a callable returning awaitables."""
    provider._client.chat = fn  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_ollama_returns_parsed_answer_dict_shape():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response(
            '{"answer_indices": [2], "confidence": 0.8, "reasoning": "ok"}'
        )

    provider = _provider()
    _install_chat(provider, chat)

    result = await provider.answer(_question())

    assert result.answer_indices == [2]
    assert result.confidence == pytest.approx(0.8)
    assert result.reasoning == "ok"
    assert result.provider == "gemma3:4b"
    assert result.from_cache is False
    assert result.latency_ms is not None and result.latency_ms >= 0


@pytest.mark.asyncio
async def test_ollama_returns_parsed_answer_object_shape():
    async def chat(**_kwargs: Any) -> Any:
        return _object_response(
            '{"answer_indices": [0], "confidence": 0.91}'
        )

    provider = _provider()
    _install_chat(provider, chat)

    result = await provider.answer(_question())
    assert result.answer_indices == [0]
    assert result.confidence == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_ollama_generic_error_classified_as_unavailable():
    async def chat(**_kwargs: Any) -> Any:
        raise RuntimeError("connection refused")

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(ProviderUnavailable):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_timeout_error_raises_provider_timeout():
    async def chat(**_kwargs: Any) -> Any:
        raise asyncio.TimeoutError()

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(ProviderTimeout):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_wait_for_timeout_when_call_is_slow():
    async def chat(**_kwargs: Any) -> Any:
        await asyncio.sleep(0.5)
        return _dict_response('{"answer_indices":[0],"confidence":0.9}')

    provider = OllamaProvider(
        host="http://localhost:11434", model="x", timeout_s=0.05
    )
    _install_chat(provider, chat)

    with pytest.raises(ProviderTimeout):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_empty_content_raises_invalid_response():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response("")

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_missing_message_key_raises_invalid_response():
    async def chat(**_kwargs: Any) -> Any:
        return {"something_else": "x"}

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_malformed_json_raises_invalid_response():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response("not json")

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(InvalidResponse):
        await provider.answer(_question())


@pytest.mark.asyncio
async def test_ollama_index_out_of_range_raises_invalid_response():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response(
            '{"answer_indices": [42], "confidence": 0.9}'
        )

    provider = _provider()
    _install_chat(provider, chat)

    with pytest.raises(InvalidResponse):
        await provider.answer(_question(n_options=3))


@pytest.mark.asyncio
async def test_ollama_single_choice_trims_extra_indices():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response(
            '{"answer_indices": [0, 1], "confidence": 0.9}'
        )

    provider = _provider()
    _install_chat(provider, chat)

    result = await provider.answer(_question(q_type="single_choice"))
    assert result.answer_indices == [0]
    assert result.confidence == pytest.approx(0.9 * 0.7)


@pytest.mark.asyncio
async def test_ollama_multiple_choice_preserves_indices():
    async def chat(**_kwargs: Any) -> Any:
        return _dict_response(
            '{"answer_indices": [0, 2], "confidence": 0.85}'
        )

    provider = _provider()
    _install_chat(provider, chat)

    result = await provider.answer(_question(q_type="multiple_choice"))
    assert result.answer_indices == [0, 2]
    assert result.confidence == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_ollama_passes_format_and_options_to_client():
    captured: dict[str, Any] = {}

    async def chat(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return _dict_response('{"answer_indices":[0],"confidence":0.9}')

    provider = _provider()
    _install_chat(provider, chat)

    await provider.answer(_question())

    assert captured["model"] == "gemma3:4b"
    assert captured["format"] == "json"
    assert captured["options"]["temperature"] == 0.1
    assert captured["options"]["num_predict"] == 200
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user"]
