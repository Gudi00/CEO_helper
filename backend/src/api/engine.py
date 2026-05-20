from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.dto import StartEngineRequest, StopEngineRequest
from src.auth import verify_token
from src.automation.manager import (
    EngineAlreadyRunning,
    EngineManager,
    EngineNotRunning,
)
from src.persistence import Session, get_session

router = APIRouter(
    prefix="/engine",
    tags=["engine"],
    dependencies=[Depends(verify_token)],
)


def _get_manager(request: Request) -> EngineManager:
    mgr = getattr(request.app.state, "engine_manager", None)
    if mgr is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ENGINE_DISABLED",
                "message": "Engine subsystem not configured",
            },
        )
    return mgr


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_engine(
    req: StartEngineRequest, request: Request
) -> dict[str, str]:
    mgr = _get_manager(request)
    async with get_session() as db:
        session = await db.get(Session, req.session_id)
        if session is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "session"},
            )
        cmid = session.cmid

    try:
        await mgr.start(
            session_id=req.session_id,
            cmid=cmid,
            access_strategy=req.access_strategy,
            cdp_port=req.cdp_port,
        )
    except EngineAlreadyRunning as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "ENGINE_RUNNING", "message": str(exc)},
        ) from exc
    return {"status": "started"}


@router.post("/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_engine(
    req: StopEngineRequest, request: Request
) -> None:
    mgr = _get_manager(request)
    try:
        await mgr.stop(req.session_id)
    except EngineNotRunning as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_RUNNING", "message": str(exc)},
        ) from exc
