from fastapi import APIRouter

from src import __version__
from src.api.dto import HealthResponse
from src.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ai_provider_primary=get_settings().gemini_model,
        version=__version__,
    )
