from src.moodle.hashing import compute_question_hash
from src.moodle.types import Option


def _options(*texts: str) -> list[Option]:
    return [Option(index=i, value=str(i + 1), text=t) for i, t in enumerate(texts)]


def test_hash_is_64_hex_lowercase():
    h = compute_question_hash("foo?", "single_choice", _options("a", "b"))
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_stable_across_option_order():
    h1 = compute_question_hash("Q", "single_choice", _options("A", "B", "C"))
    h2 = compute_question_hash("Q", "single_choice", _options("C", "A", "B"))
    assert h1 == h2


def test_hash_ignores_whitespace_and_case():
    h1 = compute_question_hash("Hello World", "single_choice", _options("a", "b"))
    h2 = compute_question_hash("  hello   WORLD  ", "single_choice", _options("A", "B"))
    assert h1 == h2


def test_hash_differs_on_type():
    a = compute_question_hash("Q", "single_choice", _options("A", "B"))
    b = compute_question_hash("Q", "multiple_choice", _options("A", "B"))
    assert a != b


def test_hash_differs_on_text():
    a = compute_question_hash("Q1", "single_choice", _options("A", "B"))
    b = compute_question_hash("Q2", "single_choice", _options("A", "B"))
    assert a != b


def test_hash_accepts_strings_or_options():
    from_options = compute_question_hash("Q", "single_choice", _options("x", "y"))
    from_strings = compute_question_hash("Q", "single_choice", ["x", "y"])
    assert from_options == from_strings
