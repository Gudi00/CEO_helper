from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src import pairing
from src.auth import EXTENSION_SCHEME, verify_token
from src.config import get_settings

router = APIRouter(prefix="/pair", tags=["pairing"])


class PairRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class PairResponse(BaseModel):
    token: str


class NewCodeResponse(BaseModel):
    code: str
    ttl_s: int


@router.post("", response_model=PairResponse)
async def pair(
    req: PairRequest, origin: str | None = Header(default=None)
) -> PairResponse:
    if not pairing.redeem(req.code):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "PAIRING_FAILED", "message": "Wrong or expired code"},
        )
    settings = get_settings()
    if origin and origin.startswith(EXTENSION_SCHEME):
        settings.add_paired_origin(origin)
    return PairResponse(token=settings.ensure_token())


@router.post(
    "/new", response_model=NewCodeResponse, dependencies=[Depends(verify_token)]
)
async def new_code() -> NewCodeResponse:
    return NewCodeResponse(code=pairing.issue_code(), ttl_s=int(pairing.CODE_TTL_S))
