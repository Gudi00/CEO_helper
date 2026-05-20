"""Bezier mouse trajectory generation for human-like cursor movement.

Used by engine to move from current cursor position to target element center.
See ADR 0007.
"""

from __future__ import annotations

import random


Point = tuple[float, float]


def bezier_curve(start: Point, end: Point, *, steps: int = 40, jitter: float = 15.0) -> list[Point]:
    """Cubic Bezier with two randomized control points.

    `steps` ≈ 60fps × 0.3-0.9s = 18-54 frames; default 40 ≈ 0.66s movement.
    """
    sx, sy = start
    ex, ey = end

    cp1 = (
        sx + (ex - sx) * 0.3 + random.uniform(-jitter, jitter),
        sy + (ey - sy) * 0.3 + random.uniform(-jitter, jitter),
    )
    cp2 = (
        sx + (ex - sx) * 0.7 + random.uniform(-jitter, jitter),
        sy + (ey - sy) * 0.7 + random.uniform(-jitter, jitter),
    )

    points: list[Point] = []
    for i in range(steps + 1):
        t = i / steps
        x = _cubic(t, sx, cp1[0], cp2[0], ex)
        y = _cubic(t, sy, cp1[1], cp2[1], ey)
        points.append((x, y))
    return points


def _cubic(t: float, p0: float, p1: float, p2: float, p3: float) -> float:
    u = 1 - t
    return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3
