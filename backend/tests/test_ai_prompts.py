from src.ai.prompts import SYSTEM_PROMPT, render_user_prompt
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _q(
    *,
    text: str = "Что такое HTTP?",
    options: tuple[str, ...] = ("Протокол", "Язык", "ОС"),
    q_type: str = "single_choice",
) -> NormalizedQuestion:
    opts = [Option(index=i, value=str(i + 1), text=t) for i, t in enumerate(options)]
    return NormalizedQuestion(
        id="q1:1",
        hash="0" * 64,
        type=q_type,
        text=text,
        options=opts,
        metadata=QuestionMetadata(
            page_number=0, attempt_id="1", cmid="1", has_images=False
        ),
    )


def test_system_prompt_demands_strict_json():
    assert "JSON" in SYSTEM_PROMPT
    assert "answer_indices" in SYSTEM_PROMPT
    assert "confidence" in SYSTEM_PROMPT
    assert "reasoning" in SYSTEM_PROMPT


def test_render_includes_question_and_indexed_options():
    out = render_user_prompt(_q())
    assert "Что такое HTTP?" in out
    assert "0) Протокол" in out
    assert "1) Язык" in out
    assert "2) ОС" in out


def test_render_single_choice_hint():
    out = render_user_prompt(_q(q_type="single_choice"))
    assert "один правильный" in out.lower()


def test_render_multiple_choice_hint():
    out = render_user_prompt(
        _q(q_type="multiple_choice", options=("a", "b", "c"))
    )
    assert "один или несколько" in out.lower()


def test_render_preserves_long_text_verbatim():
    long_text = "Текст вопроса " * 20
    out = render_user_prompt(_q(text=long_text.strip()))
    assert long_text.strip() in out
