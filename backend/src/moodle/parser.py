"""DOM parser for Moodle quiz pages — used in engine (full_auto) mode.

The extension has its own TypeScript parser for assist/step_by_step. Both
parsers must produce identical NormalizedQuestion objects from the same HTML
(verified by cross-language fixture tests). See ADR 0008.
"""

from __future__ import annotations

import copy
import re

from bs4 import BeautifulSoup, Tag

from src.moodle.hashing import compute_question_hash
from src.moodle.types import NormalizedQuestion, Option, QuestionMetadata

_QUESTION_CONTAINER = re.compile(r"^question-(\d+)-(\d+)$")
# Only strip leading "1. " / "a. " enumerators that Moodle injects via
# <span class="answernumber">. Do NOT strip "1)" — BSUIR matrix questions
# like "1) нет 2) да" legitimately contain that pattern as content.
_ANSWERNUMBER_PREFIX = re.compile(r"^[\dа-яa-z]+\.\s+", re.IGNORECASE)


class MoodleParseError(ValueError):
    """Raised when an expected element is missing from the question HTML."""


def parse_questions(
    html: str,
    *,
    cmid: str,
    page_number: int = 0,
) -> list[NormalizedQuestion]:
    """Parse every `.que` block on a page into NormalizedQuestion list.

    Tolerates both single-question and all-questions-on-page Moodle layouts.
    """
    soup = BeautifulSoup(html, "html.parser")
    questions: list[NormalizedQuestion] = []
    for container in soup.select('div.que[id^="question-"]'):
        questions.append(
            _parse_one(
                container,
                cmid=cmid,
                page_number=page_number,
            )
        )
    return questions


def _parse_one(
    container: Tag,
    *,
    cmid: str,
    page_number: int,
) -> NormalizedQuestion:
    q_id_attr = container.get("id", "")
    match = _QUESTION_CONTAINER.match(q_id_attr or "")
    if not match:
        raise MoodleParseError(f"Bad question id: {q_id_attr!r}")
    attempt_id, q_num = match.group(1), match.group(2)

    qtext = container.select_one(".qtext")
    if qtext is None:
        raise MoodleParseError(f"No .qtext in question {q_id_attr}")
    text = _clean_text(_readable_text(qtext))
    if not text:
        raise MoodleParseError(f"Empty .qtext in question {q_id_attr}")

    has_images = container.select_one(".qtext img") is not None or (
        container.select_one(".answer img") is not None
    )

    inputs = container.select(
        '.answer input[type="radio"], .answer input[type="checkbox"]'
    )
    if not inputs:
        raise MoodleParseError(f"No answer inputs in {q_id_attr}")

    is_multi = inputs[0].get("type") == "checkbox"
    options = _extract_options(container)
    if len(options) < 2:
        raise MoodleParseError(
            f"Question {q_id_attr} has {len(options)} options, expected >=2"
        )

    q_type = "multiple_choice" if is_multi else "single_choice"
    return NormalizedQuestion(
        id=f"q{attempt_id}:{q_num}",
        hash=compute_question_hash(text, q_type, options),
        type=q_type,
        text=text,
        options=options,
        metadata=QuestionMetadata(
            page_number=page_number,
            attempt_id=attempt_id,
            cmid=cmid,
            has_images=has_images,
        ),
    )


def _extract_options(container: Tag) -> list[Option]:
    options: list[Option] = []
    for idx, row in enumerate(container.select('.answer > div[class^="r"]')):
        inp = row.select_one(
            'input[type="radio"], input[type="checkbox"]'
        )
        if inp is None:
            continue
        label = row.find("label")
        source = label if label else row
        raw_text = _readable_text(source)
        text = _strip_answernumber(_clean_text(raw_text))
        if not text:
            continue
        options.append(
            Option(
                index=idx,
                value=str(inp.get("value", "")),
                text=text,
            )
        )
    return options


_MATH_RENDER_SELECTOR = (
    ".MathJax, .MathJax_Preview, .MathJax_Display, .MJX_Assistive_MathML, mjx-container"
)


def _readable_text(node: Tag) -> str:
    """Text of a node with formulas kept as source instead of rendering
    debris: a TeX-filter image becomes `[alt]`, a MathJax
    `<script type="math/tex">` becomes `$tex$`, rendered spans are dropped.
    Must stay in step with `readableText` in the extension's moodle-parser.ts.
    """
    clone = copy.copy(node)
    for el in clone.select("mjx-container"):
        tex = el.select_one('annotation[encoding="application/x-tex"]')
        if tex is not None and tex.get_text():
            el.insert_before(f" ${tex.get_text().strip()}$ ")
    for el in clone.select(_MATH_RENDER_SELECTOR):
        el.decompose()
    for el in clone.select('script[type^="math/tex"]'):
        el.replace_with(f" ${(el.string or '').strip()}$ ")
    for el in clone.select("script, style"):
        el.decompose()
    for img in clone.select("img"):
        alt = str(img.get("alt") or "").strip()
        img.replace_with(f" [{alt}] " if alt else " ")
    return clone.get_text(" ", strip=True)


def _clean_text(s: str) -> str:
    return " ".join(s.split())


def _strip_answernumber(s: str) -> str:
    return _ANSWERNUMBER_PREFIX.sub("", s).strip()
