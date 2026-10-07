"""Compare answer sources on your own questions.

    lms-tool bench bench/questions.jsonl

Each line of the file is one question with a known answer:

    {"text": "...", "type": "single_choice", "options": ["a", "b"], "correct": [0]}

Every provider configured in .env (Gemini, OpenAI-compatible, Ollama fast and
accurate) answers every question; the table shows accuracy, failures and
median latency so the model order can be chosen from numbers.
"""

from __future__ import annotations

import asyncio
import json
import statistics
from pathlib import Path

from src.ai.base import AIProvider, AIProviderError
from src.ai.gemini import GeminiProvider
from src.ai.ollama import OllamaProvider
from src.ai.openai_compat import OpenAICompatProvider
from src.config import get_settings
from src.moodle.hashing import compute_question_hash
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def load_questions(path: Path) -> list[tuple[NormalizedQuestion, list[int]]]:
    result = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        options = [
            Option(index=i, value=str(i + 1), text=text)
            for i, text in enumerate(row["options"])
        ]
        question = NormalizedQuestion(
            id=f"bench:{n}",
            hash=compute_question_hash(row["text"], row["type"], options),
            type=row["type"],
            text=row["text"],
            options=options,
            metadata=QuestionMetadata(
                page_number=0, attempt_id="bench", cmid="bench", has_images=False
            ),
        )
        result.append((question, sorted(row["correct"])))
    return result


def configured_providers() -> dict[str, AIProvider]:
    s = get_settings()
    providers: dict[str, AIProvider] = {}
    if s.gemini_api_key:
        providers[s.gemini_model] = GeminiProvider(
            api_key=s.gemini_api_key, model=s.gemini_model, timeout_s=s.gemini_timeout_s
        )
    for model in (s.openai_model, s.openai_model_accurate):
        if s.openai_base_url and model:
            providers[model] = OpenAICompatProvider(
                base_url=s.openai_base_url,
                api_key=s.openai_api_key,
                model=model,
                timeout_s=max(s.openai_timeout_s, 120.0),
            )
    if s.ollama_enabled:
        providers[s.ollama_model] = OllamaProvider(host=s.ollama_host, model=s.ollama_model)
        if s.ollama_model_accurate:
            providers[s.ollama_model_accurate] = OllamaProvider(
                host=s.ollama_host,
                model=s.ollama_model_accurate,
                timeout_s=120.0,
                think=True,
                num_predict=4096,
            )
    return providers


async def run_one(
    provider: AIProvider, questions: list[tuple[NormalizedQuestion, list[int]]]
) -> tuple[int, int, float]:
    """Return (correct, failed, median latency in seconds)."""
    correct = failed = 0
    latencies: list[float] = []
    for question, expected in questions:
        try:
            result = await provider.answer(question)
        except AIProviderError:
            failed += 1
            continue
        if sorted(result.answer_indices) == expected:
            correct += 1
        if result.latency_ms is not None:
            latencies.append(result.latency_ms / 1000)
    return correct, failed, statistics.median(latencies) if latencies else 0.0


async def main(path: Path) -> int:
    questions = load_questions(path)
    providers = configured_providers()
    if not providers:
        print("Не настроен ни один источник ответов — см. `lms-tool doctor`.")
        return 1
    total = len(questions)
    print(f"Вопросов: {total}\n")
    print(f"{'модель':<40} {'верно':>10} {'сбои':>6} {'медиана, с':>11}")
    for name, provider in providers.items():
        correct, failed, median = await run_one(provider, questions)
        share = f"{correct}/{total} ({correct / total:.0%})"
        print(f"{name:<40} {share:>10} {failed:>6} {median:>11.1f}")
    return 0


def run(path: Path) -> int:
    return asyncio.run(main(path))
