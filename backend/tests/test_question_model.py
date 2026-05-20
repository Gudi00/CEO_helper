import pytest
from pydantic import ValidationError

from src.moodle.hashing import compute_question_hash
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata


def _make_question(**overrides):
    options = [Option(index=0, value="1", text="A"), Option(index=1, value="2", text="B")]
    defaults = dict(
        id="q1:1",
        type="single_choice",
        text="Some question?",
        options=options,
        metadata=QuestionMetadata(
            page_number=0,
            attempt_id="111",
            cmid="305095",
            has_images=False,
        ),
    )
    defaults.update(overrides)
    defaults["hash"] = defaults.get(
        "hash",
        compute_question_hash(defaults["text"], defaults["type"], defaults["options"]),
    )
    return NormalizedQuestion(**defaults)


def test_valid_question_parses():
    q = _make_question()
    assert q.text == "Some question?"
    assert len(q.options) == 2


def test_rejects_short_hash():
    with pytest.raises(ValidationError):
        _make_question(hash="abc")


def test_rejects_single_option():
    with pytest.raises(ValidationError):
        _make_question(options=[Option(index=0, value="1", text="A")])


def test_rejects_unknown_type():
    with pytest.raises(ValidationError):
        _make_question(type="ordering")  # type: ignore[arg-type]


def test_immutable():
    q = _make_question()
    with pytest.raises(ValidationError):
        q.text = "changed"  # type: ignore[misc]
