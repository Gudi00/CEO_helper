from fastapi import APIRouter

from src.api import engine, health, history, models, pairing, question, session

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(pairing.router)
api_router.include_router(models.router)
api_router.include_router(session.router)
api_router.include_router(question.router)
api_router.include_router(history.router)
api_router.include_router(engine.router)

__all__ = ["api_router"]
