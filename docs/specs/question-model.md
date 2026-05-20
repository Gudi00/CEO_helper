# Question Model — JSON Schema и prompt-формат

Этот документ — единый источник истины для модели вопроса. Backend
(Pydantic) и Extension (TypeScript) должны соответствовать этой схеме.
Кодогенерация — через OpenAPI (см. [api-contract.yaml](api-contract.yaml)),
но эта спека описывает семантику.

## NormalizedQuestion JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lms-tool/schemas/question.json",
  "title": "NormalizedQuestion",
  "type": "object",
  "required": ["id", "hash", "type", "text", "options", "metadata"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Moodle-style ID, формат: q{attemptId}:{questionNum}",
      "examples": ["q739284:1", "q739284:15"]
    },
    "hash": {
      "type": "string",
      "minLength": 64,
      "maxLength": 64,
      "pattern": "^[0-9a-f]{64}$",
      "description": "SHA-256 lowercase hex от нормализованного содержимого. См. секцию 'Hashing' ниже."
    },
    "type": {
      "type": "string",
      "enum": ["single_choice", "multiple_choice"]
    },
    "text": {
      "type": "string",
      "minLength": 1,
      "description": "Plain text вопроса. HTML stripped. MathJax → '$$..$$' placeholders."
    },
    "options": {
      "type": "array",
      "minItems": 2,
      "items": {
        "type": "object",
        "required": ["index", "value", "text"],
        "properties": {
          "index": {
            "type": "integer",
            "minimum": 0,
            "description": "0-based, отображается в prompt и UI"
          },
          "value": {
            "type": "string",
            "description": "value атрибут <input>, используется при submit формы"
          },
          "text": {
            "type": "string",
            "minLength": 1,
            "description": "Plain text варианта без 'N. ' префикса"
          }
        }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["page_number", "attempt_id", "cmid", "has_images"],
      "properties": {
        "page_number": { "type": "integer", "minimum": 0 },
        "attempt_id": { "type": "string" },
        "cmid": { "type": "string" },
        "has_images": {
          "type": "boolean",
          "description": "true если в .qtext или .answer есть <img>. MVP: помечаем, но не обрабатываем."
        }
      }
    }
  }
}
```

## Hashing

Цель — стабильный хеш одинакового вопроса в разных попытках/студентах.

Алгоритм:

```python
def compute_hash(question: NormalizedQuestion) -> str:
    normalized_text = normalize_whitespace(question["text"])
    sorted_options = sorted(
        normalize_whitespace(opt["text"]) for opt in question["options"]
    )
    payload = (
        normalized_text + "\n" +
        question["type"] + "\n" +
        "|".join(sorted_options)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_whitespace(s: str) -> str:
    # Collapse runs of whitespace + casefold + strip
    return " ".join(s.split()).casefold()
```

**Что НЕ входит в hash:**
- `id` (он включает attempt_id, который меняется)
- `value` атрибуты (Moodle randomize-ит порядок и values)
- `metadata` (страница, попытка)

Это даёт стабильный кеш-ключ через разные сессии.

## TypeScript тип (для extension)

Генерируется из OpenAPI через `openapi-typescript`. Эквивалент:

```typescript
export type QuestionType = "single_choice" | "multiple_choice";

export interface Option {
  index: number;
  value: string;
  text: string;
}

export interface QuestionMetadata {
  page_number: number;
  attempt_id: string;
  cmid: string;
  has_images: boolean;
}

export interface NormalizedQuestion {
  id: string;
  hash: string;
  type: QuestionType;
  text: string;
  options: Option[];
  metadata: QuestionMetadata;
}
```

## Pydantic модель (для backend)

```python
from pydantic import BaseModel, Field
from typing import Literal

QuestionType = Literal["single_choice", "multiple_choice"]

class Option(BaseModel):
    index: int = Field(ge=0)
    value: str
    text: str = Field(min_length=1)

class QuestionMetadata(BaseModel):
    page_number: int = Field(ge=0)
    attempt_id: str
    cmid: str
    has_images: bool

class NormalizedQuestion(BaseModel):
    id: str
    hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    type: QuestionType
    text: str = Field(min_length=1)
    options: list[Option] = Field(min_length=2)
    metadata: QuestionMetadata
```

## Prompt-template для AI

Шаблон промпта в `backend/src/ai/prompts.py`:

```python
SYSTEM_PROMPT = """\
Ты — эксперт, помогающий студенту проверить ответы на тесте.
Внимательно читаешь вопрос и варианты, выбираешь правильный(е).

Отвечай СТРОГО в формате JSON, без дополнительного текста:
{
  "answer_indices": [<list of 0-based indices>],
  "confidence": <float 0..1>,
  "reasoning": "<краткое объяснение, до 200 символов>"
}

Для single_choice — answer_indices содержит ровно один индекс.
Для multiple_choice — один или несколько.
confidence отражает твою уверенность: 0.95+ только когда абсолютно
уверен, 0.5-0.7 для рискованных ответов, ниже — не угадывай.
"""

USER_PROMPT_TEMPLATE = """\
Тип вопроса: {q_type_human}
Вопрос:
{q_text}

Варианты ответа:
{options_block}
"""


def render_user_prompt(q: NormalizedQuestion) -> str:
    q_type_human = (
        "выбери один правильный вариант"
        if q.type == "single_choice"
        else "выбери один или несколько правильных вариантов"
    )
    options_block = "\n".join(
        f"{opt.index}) {opt.text}" for opt in q.options
    )
    return USER_PROMPT_TEMPLATE.format(
        q_type_human=q_type_human,
        q_text=q.text,
        options_block=options_block,
    )
```

### Параметры вызова Gemini

| Param | Value | Why |
|---|---|---|
| `model` | `gemini-2.0-flash` (default) | Быстрая, бесплатная |
| `temperature` | `0.1` | Хотим стабильности, не креативности |
| `max_output_tokens` | `1024` | JSON + reasoning ≤ 200 chars влезает |
| `response_mime_type` | `application/json` | Заставит модель вернуть строгий JSON |
| `top_p` | `0.95` | Default |

### Параметры вызова Ollama (Gemma)

| Param | Value |
|---|---|
| `model` | `gemma3:4b` |
| `format` | `json` |
| `options.temperature` | `0.1` |
| `options.num_predict` | `200` |

## Парсинг ответа AI

```python
import json
from pydantic import BaseModel, Field

class RawAIResponse(BaseModel):
    answer_indices: list[int] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    reasoning: str | None = None

def parse_ai_response(raw: str, q: NormalizedQuestion) -> RawAIResponse:
    data = json.loads(raw)
    parsed = RawAIResponse(**data)

    # Валидация против вопроса
    max_index = len(q.options) - 1
    if any(i < 0 or i > max_index for i in parsed.answer_indices):
        raise ValueError(f"AI returned out-of-range index in {parsed.answer_indices}")
    if q.type == "single_choice" and len(parsed.answer_indices) != 1:
        # Берём первый, понижаем confidence
        parsed.answer_indices = parsed.answer_indices[:1]
        parsed.confidence *= 0.7

    return parsed
```

## Примеры

### Single choice

```json
{
  "id": "q739284:3",
  "hash": "a3c5...64hex",
  "type": "single_choice",
  "text": "В каком году была основана БГУИР?",
  "options": [
    { "index": 0, "value": "1", "text": "1964" },
    { "index": 1, "value": "2", "text": "1967" },
    { "index": 2, "value": "3", "text": "1971" },
    { "index": 3, "value": "4", "text": "1980" }
  ],
  "metadata": {
    "page_number": 2,
    "attempt_id": "739284",
    "cmid": "305095",
    "has_images": false
  }
}
```

AI вернёт:
```json
{ "answer_indices": [2], "confidence": 0.92, "reasoning": "БГУИР основан в 1964 году как МРТИ" }
```

Wait — reasoning противоречит индексу. Это пример **ошибки AI**. Парсер
не ловит логические противоречия — он только валидирует структуру.
Поэтому `confidence` критичен: при <0.7 предупреждаем юзера.

### Multiple choice

```json
{
  "id": "q739284:7",
  "type": "multiple_choice",
  "text": "Какие из перечисленных языков являются интерпретируемыми?",
  "options": [
    { "index": 0, "value": "1", "text": "Python" },
    { "index": 1, "value": "2", "text": "C++" },
    { "index": 2, "value": "3", "text": "JavaScript" },
    { "index": 3, "value": "4", "text": "Rust" }
  ]
}
```

AI:
```json
{ "answer_indices": [0, 2], "confidence": 0.99, "reasoning": "Python и JS — интерпретируемые; C++/Rust компилируемые" }
```
