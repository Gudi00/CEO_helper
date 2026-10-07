from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.auth import verify_token
from src.config import get_settings

router = APIRouter(tags=["models"], dependencies=[Depends(verify_token)])


class ModelInfo(BaseModel):
    id: str
    model: str


@router.get("/models", response_model=list[ModelInfo])
async def list_models(request: Request) -> list[ModelInfo]:
    """Model preferences the backend can actually serve right now."""
    providers: dict[str, object] = getattr(request.app.state, "ai_providers", {})
    settings = get_settings()
    return [
        ModelInfo(id=key, model=settings.model_label(key) or getattr(p, "name", key))
        for key, p in providers.items()
    ]
