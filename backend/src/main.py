from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import __version__
from src.ai.base import AIProvider
from src.ai.cascade import CascadeProvider
from src.ai.gemini import GeminiProvider
from src.ai.ollama import OllamaProvider
from src.api import api_router
from src.api.ws import broadcast as ws_broadcast
from src.api.ws import router as ws_router
from src.automation.browser import Browser
from src.automation.manager import EngineManager
from src.config import get_settings
from src.persistence.db import init_db


def _build_ai_providers() -> dict[str, AIProvider]:
    """Build named providers: 'fast' (cascade Gemini→Ollama) and 'accurate' (local thinking model)."""
    settings = get_settings()
    result: dict[str, AIProvider] = {}

    fast_chain: list[AIProvider] = []
    if settings.gemini_api_key:
        fast_chain.append(
            GeminiProvider(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_s=settings.gemini_timeout_s,
            )
        )
    if settings.ollama_enabled:
        fast_chain.append(
            OllamaProvider(host=settings.ollama_host, model=settings.ollama_model)
        )

    if fast_chain:
        result["fast"] = fast_chain[0] if len(fast_chain) == 1 else CascadeProvider(fast_chain)

    if settings.ollama_enabled and settings.ollama_model_accurate:
        result["accurate"] = OllamaProvider(
            host=settings.ollama_host,
            model=settings.ollama_model_accurate,
            timeout_s=120.0,
            think=True,
            num_predict=4096,
            num_gpu=99,
        )

    return result


def _build_ai_provider() -> AIProvider | None:
    providers = _build_ai_providers()
    if not providers:
        return None
    return providers.get("accurate") or next(iter(providers.values()))


async def _default_browser_factory(
    access_strategy: str, cdp_port: int
) -> Browser:
    """Production browser factory — lazily imports SeleniumBrowser so the
    backend can boot without the `[engine]` extras installed.
    """
    from src.automation.selenium_browser import SeleniumBrowser

    if access_strategy == "cdp":
        return await SeleniumBrowser.attach_cdp(port=cdp_port)
    if access_strategy == "manual_login":
        return await SeleniumBrowser.launch_new()
    raise ValueError(f"unsupported access strategy: {access_strategy!r}")


def _build_engine_manager(
    ai_provider: AIProvider | None,
    *,
    browser_factory: Any = None,
) -> EngineManager | None:
    if ai_provider is None:
        return None

    def ai_factory() -> AIProvider:
        return ai_provider

    async def broadcast(session_id: UUID, message: dict[str, Any]) -> None:
        await ws_broadcast(session_id, message)

    return EngineManager(
        browser_factory=browser_factory or _default_browser_factory,
        ai_factory=ai_factory,
        broadcast=broadcast,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=get_settings().log_level)
    await init_db()
    get_settings().ensure_token()

    # Tests may pre-populate these on app.state before entering the lifespan.
    if not hasattr(app.state, "ai_providers"):
        app.state.ai_providers = _build_ai_providers()
    if not hasattr(app.state, "ai_provider"):
        app.state.ai_provider = _build_ai_provider()
    if not hasattr(app.state, "engine_manager"):
        factory = getattr(app.state, "browser_factory", None)
        app.state.engine_manager = _build_engine_manager(
            app.state.ai_provider, browser_factory=factory
        )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="LMS Quiz Backend",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^chrome-extension://.*$",
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
