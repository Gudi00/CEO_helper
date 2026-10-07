from pathlib import Path

import pytest

from src.moodle.parser import MoodleParseError, parse_questions

FIXTURES = Path(__file__).parent / "fixtures" / "moodle"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_single_choice_parsed():
    qs = parse_questions(_read("single_choice.html"), cmid="305095")
    assert len(qs) == 1
    q = qs[0]
    assert q.id == "q739284:1"
    assert q.type == "single_choice"
    assert "БГУИР" in q.text
    assert [o.text for o in q.options] == ["1964", "1967", "1971", "1980"]
    assert [o.value for o in q.options] == ["1", "2", "3", "4"]
    assert q.metadata.attempt_id == "739284"
    assert q.metadata.cmid == "305095"
    assert q.metadata.has_images is False
    assert len(q.hash) == 64


def test_multiple_choice_parsed():
    qs = parse_questions(_read("multiple_choice.html"), cmid="305095")
    assert len(qs) == 1
    q = qs[0]
    assert q.id == "q739284:7"
    assert q.type == "multiple_choice"
    assert "интерпретируемыми" in q.text
    texts = [o.text for o in q.options]
    assert texts == ["Python", "C++", "JavaScript", "Rust"]


def test_multi_question_page_parses_all():
    qs = parse_questions(
        _read("multi_question_page.html"), cmid="305095", page_number=2
    )
    assert [q.id for q in qs] == ["q739284:3", "q739284:4"]
    assert all(q.metadata.page_number == 2 for q in qs)
    assert qs[0].options[0].text == "Протокол передачи гипертекста"
    assert qs[1].options[1].text == "443"


def test_image_flag_set_when_img_present():
    qs = parse_questions(_read("with_image.html"), cmid="305095")
    assert len(qs) == 1
    assert qs[0].metadata.has_images is True


def test_hash_stable_across_runs():
    qs1 = parse_questions(_read("single_choice.html"), cmid="305095")
    qs2 = parse_questions(_read("single_choice.html"), cmid="305095")
    assert qs1[0].hash == qs2[0].hash


def test_empty_html_returns_empty_list():
    assert parse_questions("<div></div>", cmid="305095") == []


def test_malformed_question_id_raises():
    # Container matches the .que[id^="question-"] selector but the id doesn't
    # match the question-<attempt>-<num> shape — should raise instead of being
    # silently skipped.
    bad = (
        '<div class="que" id="question-bad">'
        '<div class="qtext">x</div>'
        '<div class="answer"><div class="r0">'
        '<input type="radio" name="x" value="1">'
        '<label>x</label></div></div>'
        "</div>"
    )
    with pytest.raises(MoodleParseError):
        parse_questions(bad, cmid="305095")


def test_answernumber_prefix_stripped():
    qs = parse_questions(_read("single_choice.html"), cmid="305095")
    for opt in qs[0].options:
        assert not opt.text.startswith(("1.", "2.", "3.", "4."))


def test_tex_image_is_kept_as_alt_text():
    qs = parse_questions(_read("with_image.html"), cmid="1")
    assert qs[0].text == "Решите уравнение: [x^2 = 4]"


def test_mathjax_source_is_kept_and_rendered_copy_dropped():
    html = """
      <div class="que multichoice" id="question-1-1">
        <div class="qtext">Чему равно
          <span class="MathJax_Preview">junk</span>
          <span class="MathJax"><span>x2</span></span>
          <script type="math/tex">x^2</script> при x = 3?
        </div>
        <div class="answer">
          <div class="r0"><input type="radio" value="1"><label>6</label></div>
          <div class="r1"><input type="radio" value="2"><label>
            <mjx-container><mjx-math>9</mjx-math><mjx-assistive-mml><math><semantics>
              <mn>9</mn><annotation encoding="application/x-tex">3^2</annotation>
            </semantics></math></mjx-assistive-mml></mjx-container></label></div>
        </div>
      </div>"""
    q = parse_questions(html, cmid="1")[0]
    assert q.text == "Чему равно $x^2$ при x = 3?"
    assert [o.text for o in q.options] == ["6", "$3^2$"]
