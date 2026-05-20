"""Opt-in live smoke test against the real Gemini API.

Skipped unless the environment variable `LIVE_GEMINI_API_KEY` is set
(a separate name from `GEMINI_API_KEY` so the regular conftest can blank
the production env without affecting this test).

Run with:
    LIVE_GEMINI_API_KEY=AIza... .venv/bin/pytest tests/test_ai_gemini_live.py -v

Network-bound and non-deterministic; do NOT include in CI by default.
"""

from __future__ import annotations

import os

import pytest

from src.ai.gemini import GeminiProvider
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata

_LIVE_KEY = os.environ.get("LIVE_GEMINI_API_KEY") or ""
_MODEL = os.environ.get("LIVE_GEMINI_MODEL", "gemini-2.0-flash")

pytestmark = pytest.mark.skipif(
    not _LIVE_KEY,
    reason="LIVE_GEMINI_API_KEY not set — skipping live Gemini test",
)


def _easy_question() -> NormalizedQuestion:
    """A question whose correct answer is obvious for any half-decent LLM."""
    options = [
        Option(index=0, value="1", text="Париж"),
        Option(index=1, value="2", text="Лондон"),
        Option(index=2, value="3", text="Берлин"),
        Option(index=3, value="4", text="Мадрид"),
    ]
    return NormalizedQuestion(
        id="q1:1",
        hash="f" * 64,
        type="single_choice",
        text="Какой город является столицей Франции?",
        options=options,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="1", cmid="0", has_images=False
        ),
    )


@pytest.mark.asyncio
async def test_live_gemini_returns_correct_answer_for_trivial_question():
    provider = GeminiProvider(api_key=_LIVE_KEY, model=_MODEL, timeout_s=15.0)
    result = await provider.answer(_easy_question())

    assert result.provider == _MODEL
    assert result.answer_indices == [0]  # Париж
    assert result.confidence > 0.7
    assert result.latency_ms is not None and result.latency_ms < 15_000
