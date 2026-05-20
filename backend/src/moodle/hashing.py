import hashlib

from src.moodle.types import NormalizedQuestion, Option, QuestionType


def _normalize_whitespace(s: str) -> str:
    return " ".join(s.split()).casefold()


def compute_question_hash(
    text: str,
    q_type: QuestionType,
    options: list[Option] | list[str],
) -> str:
    """Stable SHA-256 hash of question identity. See docs/specs/question-model.md.

    Order-independent over options (sorted before hashing) so randomized Moodle
    option ordering does not break the cache.
    """
    normalized_text = _normalize_whitespace(text)
    option_texts: list[str] = [
        _normalize_whitespace(o.text if isinstance(o, Option) else o) for o in options
    ]
    payload = "\n".join([normalized_text, q_type, "|".join(sorted(option_texts))])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_of(q: NormalizedQuestion) -> str:
    return compute_question_hash(q.text, q.type, list(q.options))
