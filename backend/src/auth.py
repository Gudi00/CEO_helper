from secrets import compare_digest

from fastapi import Header, HTTPException, status

from src.config import get_settings

EXTENSION_SCHEME = "chrome-extension://"


async def verify_token(
    x_backend_token: str | None = Header(default=None),
    origin: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    expected = settings.ensure_token()
    if not x_backend_token or not compare_digest(
        x_backend_token.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Bad X-Backend-Token"},
        )
    # Once an extension has paired, other extensions in the same browser are
    # refused even if they somehow obtained the token. Until then (token
    # pasted by hand, CLI, tests) the origin is not restricted.
    if origin and origin.startswith(EXTENSION_SCHEME):
        paired = settings.paired_origins()
        if paired and origin not in paired:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ORIGIN_NOT_PAIRED", "message": "Extension is not paired"},
            )
