from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# The browser tests import Playwright at collection time; without it
# installed (CI, a plain dev setup) the whole directory is left out.
collect_ignore = [] if importlib.util.find_spec("playwright") else ["e2e"]


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("BACKEND_TOKEN", "test-token")
    monkeypatch.setenv("PAIRED_ORIGINS_FILE", str(tmp_path / "paired_origins"))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OLLAMA_ENABLED", "false")

    from src.config import get_settings
    get_settings.cache_clear()

    import src.persistence.db as db_mod
    db_mod._engine = None
    db_mod._session_factory = None

    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from src.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            c.headers["X-Backend-Token"] = "test-token"
            yield c
