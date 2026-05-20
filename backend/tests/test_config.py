"""Regression test for the inline-comment stripping introduced after we
discovered pydantic-settings was treating `KEY=  # comment` as the value.
"""

from __future__ import annotations

import pytest

from src.config import Settings


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("token123", "token123"),
        ("  spaced  ", "spaced"),
        ("# pure comment", ""),
        ("real-token   # inline note", "real-token"),
        ("tok#fragment", "tok"),  # fragment included by accident → stripped
        ("", ""),
    ],
)
def test_strip_inline_comment_on_backend_token(raw: str, expected: str):
    s = Settings(backend_token=raw)
    assert s.backend_token == expected


def test_strip_inline_comment_on_gemini_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaXYZ   # do-not-commit")
    monkeypatch.setenv("BACKEND_TOKEN", "")
    s = Settings()
    assert s.gemini_api_key == "AIzaXYZ"


def test_non_string_fields_are_untouched():
    s = Settings(backend_port=9000)
    assert s.backend_port == 9000
