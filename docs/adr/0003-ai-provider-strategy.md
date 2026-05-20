# ADR 0003: AI provider — Gemini Pro primary + локальная Gemma fallback

## Status

Accepted, 2026-05-17

## Context

Нужно отвечать на тестовые вопросы (текст + варианты, в Phase 2 — изображения).
Ограничения:

- Бесплатный/дешёвый tier (стажировка, бюджета на API ~0).
- Поддержка русского языка на высоком уровне (BSUIR контент русскоязычный).
- Multimodal support (для Phase 2 с MathJax PNG).
- Возможность fallback на локальную модель если облако недоступно / квота
  закончилась / privacy.
- Видеокарта пользователя: RTX 2060 6 ГБ VRAM, 16 ГБ RAM.

Рассматривались варианты.

| Provider | Pros | Cons |
|---|---|---|
| Anthropic Claude | Лучшее качество reasoning | Платный, нет free tier |
| OpenAI GPT-4 | Качество | Платный |
| **Gemini Pro** | **Бесплатный tier, vision, RU support** | Rate limits, иногда отказы |
| DeepSeek API | Бесплатно | Слабее на узкоспец вопросах, нет vision |
| Локальная LLM | Privacy, бесплатно | Качество ниже, нужно железо |

Для локального fallback на 6 ГБ VRAM подходит:
- Gemma 3 1B — слишком слабо для специфичных вопросов
- **Gemma 3 4B Q5_K_M** — ~3.5 ГБ VRAM, хороший компромис ← выбран
- Gemma 3 12B Q4 — ~7-8 ГБ VRAM, не влезет полностью, нужен CPU offload
- Qwen 2.5 7B — альтернатива, схожее качество, ~5 ГБ VRAM в Q4

## Decision

**Primary:** Gemini Pro (стартовая модель — `gemini-2.0-flash`, fallback
внутри Gemini — `gemini-2.0-pro` при низкой уверенности).

**Fallback (Phase 1.5):** Gemma 3 4B Q5_K_M через Ollama, локально.

**Архитектура:**

```python
# backend/src/ai/base.py
class AIProvider(Protocol):
    async def answer(
        self,
        question: NormalizedQuestion,
    ) -> AnswerResult: ...

class AnswerResult(BaseModel):
    answer_indices: list[int]      # выбранные варианты (для radio — один, для checkbox — несколько)
    confidence: float              # 0..1, model self-reported
    reasoning: str | None          # для логов
    provider: str                  # "gemini-2.0-flash" / "gemma3:4b"
```

**Cascade-логика** в фабрике провайдеров:

```
1. GeminiProvider.answer()
   - success → return
   - quota/429/503 → fall to Ollama
   - confidence < 0.5 → retry with gemini-2.0-pro
   - timeout (>10s) → fall to Ollama
2. OllamaProvider.answer()
   - success → return (но помечается в логах как fallback)
   - failure → AnswerResult с answer_indices=[0], confidence=0.0
                и явным флагом "failed" — пусть пользователь решит
```

**Prompting:** см. шаблон в [specs/question-model.md](../specs/question-model.md#prompt-template).
Ключевые принципы:

- Промпт на русском (вопросы и так на русском, перевод теряет смысл).
- Просим вернуть JSON с `answer_indices`, `confidence`, `reasoning`.
- В system message: "Ты эксперт в [предметной области теста]" — область
  определяется по `cmid` (пользователь задаёт в popup), хранится в сессии.
- Temperature: 0.1 (хотим стабильности, не креативности).

**Кеширование** — см. [0009](0009-data-persistence.md). Хеш SHA-256 от
нормализованного текста вопроса+вариантов → ответ. При повторе берём из БД,
не дёргаем API.

## Consequences

### Положительные
- Бесплатно в обычном режиме (Gemini free tier ~15 req/min, теста на 20 вопросов хватает).
- Privacy fallback готов к запуску — Gemma 3 4B уместится в 6 ГБ VRAM.
- Provider-агностичный интерфейс — легко добавить ещё (Claude, GPT) позже.
- Кеш экономит запросы при повторных попытках одного теста.

### Отрицательные
- Gemma 3 4B заметно слабее Gemini на сложных вопросах (по неформальным
  бенчмаркам потеря ~10-20% точности). Mitigation: помечаем fallback-ответы
  в overlay расширения иконкой, пользователь видит что это fallback.
- Gemini Pro меняет API endpoints/модели — нужно периодически обновлять
  `GEMINI_MODEL` в .env. Mitigation: фиксированная зависимость + README.

### Sized
- Gemini Pro latency: 0.5-2s на ответ.
- Gemma 3 4B на RTX 2060: ~1.5-4s на ответ (зависит от длины контекста).

## Alternatives considered

### LiteLLM как абстракция
LiteLLM проксирует разные провайдеры за единым API. Соблазнительно, но:
для двух провайдеров (Gemini + Ollama) добавляет overhead зависимостей,
свой Pydantic-слой, и сложнее отлаживать. Решено: писать тонкий
`AIProvider` интерфейс самим.

### Использовать Anthropic Claude API
Качество выше, но требует платной подписки. Для стажировочного проекта
с бесплатным tier-ом Gemini достаточно. Можно добавить как `ClaudeProvider`
в Phase 4 если будет ключ.

### Только локальная LLM (без облака)
Privacy идеален, но: 4B-модели проигрывают по точности на специальных
терминах; нужна установка Ollama для всех пользователей. Решено: облако
по умолчанию, локалка опциональна.

### Гибридный prompt: текст в Gemma, "сложные" в Gemini
Самооценка сложности самой моделью — ненадёжно. Каскад "сначала Gemini,
при отказе Gemma" проще и логичнее.

## Review notes

- Названия моделей Gemini меняются: `gemini-2.0-flash` актуально на
  2026-05-17. Перепроверить при выходе кода в Phase 1.
- Когда выйдет Gemma 3 27B в правильном размере под 6 ГБ — рассмотреть
  замену.
