from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.persistence.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_engine() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        url = get_settings().database_url
        # SQLite creates the file but not the folder it lives in.
        if url.startswith("sqlite") and ":///" in url:
            Path(url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(
            url,
            future=True,
            echo=False,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Create tables for dev. Production uses Alembic — see backend/alembic/."""
    _ensure_engine()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    factory = _ensure_engine()
    async with factory() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise
