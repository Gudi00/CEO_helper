"""Tiny FastAPI app that mimics enough of Moodle to drive content-script
tests. The URL shape mirrors the real LMS:

    GET /mod/quiz/attempt.php?attempt=<id>&cmid=<id>&page=<n>

The HTML body is whatever the test puts in `page_state["html"]` — usually
one of the fixture files in `backend/tests/fixtures/moodle/`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def create_mock_app(initial_html: str) -> tuple[FastAPI, dict[str, Any]]:
    state: dict[str, Any] = {"html": initial_html, "request_count": 0}
    app = FastAPI(title="mock-moodle")

    def _page(html_body: str) -> str:
        return (
            "<!doctype html><html lang=ru><head><meta charset=utf-8>"
            "<title>Mock Moodle Quiz</title></head><body>"
            "<header><h1>Mock Moodle Quiz</h1></header>"
            f"{html_body}"
            "</body></html>"
        )

    @app.get("/mod/quiz/attempt.php", response_class=HTMLResponse)
    async def quiz_attempt() -> str:
        state["request_count"] += 1
        return _page(state["html"])

    return app, state
