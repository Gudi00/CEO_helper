from src.moodle.types import NormalizedQuestion

# Appended to every system prompt (default or custom) — the model MUST see
# this regardless of what the user writes, otherwise JSON parsing breaks.
JSON_FORMAT_INSTRUCTION = """\
Отвечай СТРОГО в формате JSON, БЕЗ markdown, БЕЗ преамбулы:
{
  "answer_indices": [<список 0-based индексов>],
  "confidence": <float 0..1>,
  "reasoning": "<краткое — до 200 символов — обоснование>"
}

Для single_choice — answer_indices содержит ровно один индекс.
Для multiple_choice — один или несколько.
confidence: 0.95+ абсолютно уверен · 0.75-0.94 уверен · 0.5-0.74 сомнения · <0.5 не угадывай.\
"""

_DEFAULT_ROLE = """\
Ты — преподаватель технического вуза (информатика, программирование,
электроника, сети). Помогаешь студенту проверить ответ на тесте.

Алгоритм мышления (выполняй внутренне перед ответом):
  1. Перефразируй вопрос своими словами — что именно спрашивают.
  2. Идентифицируй область знаний (язык, протокол, алгоритм, ОС).
  3. Для каждого варианта объясни, почему он верен или неверен.
  4. Выбери индекс(ы) и оцени уверенность.
  5. Если хотя бы 2 варианта выглядят правдоподобно — confidence ≤ 0.7.
  6. Если вопрос содержит конструкцию "1) X 2) Y" внутри варианта
     (matrix-формат), он спрашивает совокупность утверждений в порядке —
     не путай с нумерацией вариантов.\
"""

SYSTEM_PROMPT = _DEFAULT_ROLE + "\n\n" + JSON_FORMAT_INSTRUCTION


def build_system_prompt(custom: str | None) -> str:
    """Return effective system prompt: custom role + mandatory JSON block."""
    role = custom.strip() if custom and custom.strip() else _DEFAULT_ROLE
    return role + "\n\n" + JSON_FORMAT_INSTRUCTION


def render_user_prompt(q: NormalizedQuestion) -> str:
    q_type_human = (
        "выбери ОДИН правильный вариант"
        if q.type == "single_choice"
        else "выбери ОДИН ИЛИ НЕСКОЛЬКО правильных вариантов"
    )
    options_block = "\n".join(f"  {opt.index}) {opt.text}" for opt in q.options)
    images_note = (
        f"К вопросу приложено изображений: {len(q.images)} — учитывай их.\n"
        if q.images
        else ""
    )
    return (
        f"Тип вопроса: {q_type_human}\n"
        f"{images_note}"
        f"Вопрос:\n{q.text}\n\n"
        f"Варианты ответа (индексы 0-based):\n{options_block}\n\n"
        "Верни ТОЛЬКО JSON-объект, описанный в system message."
    )
