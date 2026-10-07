"""One-time pairing codes: the extension trades a short code shown in the
backend console for the backend token, so the user never copies the token
by hand. State is in-process — a restart simply invalidates the code.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from secrets import compare_digest, randbelow

CODE_TTL_S = 120.0
MAX_FAILURES = 5


@dataclass
class _Pending:
    code: str
    expires_at: float
    failures: int = 0


_pending: _Pending | None = None


def issue_code() -> str:
    """Create a fresh 6-digit code, replacing any previous one."""
    global _pending
    code = f"{randbelow(1_000_000):06d}"
    _pending = _Pending(code=code, expires_at=time.monotonic() + CODE_TTL_S)
    return code


def redeem(code: str) -> bool:
    """Return True and burn the code if it matches. A wrong guess counts
    against MAX_FAILURES, after which the code is dropped.
    """
    global _pending
    if _pending is None:
        return False
    if time.monotonic() > _pending.expires_at:
        _pending = None
        return False
    if compare_digest(code.encode(), _pending.code.encode()):
        _pending = None
        return True
    _pending.failures += 1
    if _pending.failures >= MAX_FAILURES:
        _pending = None
    return False


def reset() -> None:
    global _pending
    _pending = None
