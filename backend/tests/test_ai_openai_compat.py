from __future__ import annotations

import json

import httpx
import pytest

from src.ai.base import InvalidResponse, ProviderUnavailable, QuotaExceeded
from src.ai.openai_compat import OpenAICompatProvider
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _q() -> NormalizedQuestion:
    options = [Option(index=i, value=str(i + 1), text=f"opt{i}") for i in range(3)]
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


def _provider(handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        base_url="https://api.example/v1/",
        model="some-model",
        api_key="k",
        transport=httpx.MockTransport(handler),
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.mark.asyncio
async def test_answer_parses_json_and_sends_auth():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return _completion('{"answer_indices": [2], "confidence": 0.9, "reasoning": "r"}')

    result = await _provider(handler).answer(_q())

    assert result.answer_indices == [2]
    assert result.provider == "some-model"
    assert seen["url"] == "https://api.example/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "some-model"  # type: ignore[index]


@pytest.mark.asyncio
async def test_answer_tolerates_think_block_and_code_fence():
    content = (
        "<think>hmm {not json}</think>\n```json\n"
        '{"answer_indices": [0], "confidence": 0.8}\n```'
    )
    result = await _provider(lambda _r: _completion(content)).answer(_q())
    assert result.answer_indices == [0]


@pytest.mark.asyncio
async def test_out_of_range_index_is_invalid():
    content = '{"answer_indices": [7], "confidence": 0.8}'
    with pytest.raises(InvalidResponse):
        await _provider(lambda _r: _completion(content)).answer(_q())


@pytest.mark.asyncio
async def test_http_429_maps_to_quota_exceeded():
    with pytest.raises(QuotaExceeded):
        await _provider(lambda _r: httpx.Response(429)).answer(_q())


@pytest.mark.asyncio
async def test_http_500_maps_to_unavailable():
    with pytest.raises(ProviderUnavailable):
        await _provider(lambda _r: httpx.Response(500)).answer(_q())


@pytest.mark.asyncio
async def test_images_are_sent_as_data_urls():
    from src.moodle.types import QuestionImage

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _completion('{"answer_indices": [0], "confidence": 0.9}')

    q = _q().model_copy(update={"images": [QuestionImage(mime="image/png", data="aGk=")]})
    await _provider(handler).answer(q)

    content = seen["body"]["messages"][1]["content"]  # type: ignore[index]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,aGk="
