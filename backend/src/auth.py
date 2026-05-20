from fastapi import Header, HTTPException, status

from src.config import get_settings


async def verify_token(
    x_backend_token: str | None = Header(default=None),
) -> None:
    expected = get_settings().ensure_token()
    if not x_backend_token or x_backend_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Bad X-Backend-Token"},
        )
