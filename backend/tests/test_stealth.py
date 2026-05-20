"""Statistical tests for stealth timing + geometry. Asserts shape over many
samples rather than specific values (RNG-stable but not predictable).
"""

from __future__ import annotations

import math
import random
import statistics

import pytest

from src.stealth.delays import (
    before_submit_s,
    between_clicks_s,
    between_pages_s,
    reading_delay_s,
)
from src.stealth.mouse import bezier_curve

SAMPLES = 500


@pytest.fixture(autouse=True)
def _stable_rng():
    random.seed(42)
    yield


def test_between_clicks_within_documented_window():
    samples = [between_clicks_s() for _ in range(SAMPLES)]
    assert all(0.4 <= s <= 1.2 for s in samples)
    assert 0.5 < statistics.mean(samples) < 1.1


def test_between_pages_within_documented_window():
    samples = [between_pages_s() for _ in range(SAMPLES)]
    assert all(0.8 <= s <= 2.5 for s in samples)


def test_before_submit_within_documented_window():
    samples = [before_submit_s() for _ in range(SAMPLES)]
    assert all(3.0 <= s <= 7.0 for s in samples)


@pytest.mark.parametrize("length", [10, 80, 320, 1200])
def test_reading_delay_scales_with_text_length(length: int):
    samples = [reading_delay_s(length) for _ in range(200)]
    avg = statistics.mean(samples)
    # The baseline is clamped to [2, 8]; expected within ±jitter of that.
    expected_baseline = max(2.0, min(8.0, length / 80))
    lower = expected_baseline * 0.6
    upper = expected_baseline * 1.4
    assert lower <= avg <= upper


def test_reading_delay_clamped_at_eight_seconds_for_huge_text():
    # Without clamp, length 10000 chars → 125s. With clamp → max ~8 + jitter.
    samples = [reading_delay_s(10000) for _ in range(200)]
    assert max(samples) < 12.0  # clamp_high (8) + 0.4 * 8 = 11.2


def test_bezier_curve_endpoints():
    start = (0.0, 0.0)
    end = (100.0, 200.0)
    pts = bezier_curve(start, end, steps=40, jitter=0)
    assert pts[0] == pytest.approx(start)
    assert pts[-1] == pytest.approx(end)
    assert len(pts) == 41


def test_bezier_curve_smooth_steps():
    pts = bezier_curve((0.0, 0.0), (200.0, 0.0), steps=60, jitter=0)
    # Successive distances should not jump wildly — every step under ~2x
    # the average distance.
    dists = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    avg = statistics.mean(dists)
    assert max(dists) < avg * 2.5


def test_bezier_curve_jitter_introduces_variation():
    a = bezier_curve((0.0, 0.0), (100.0, 100.0), steps=20, jitter=15)
    b = bezier_curve((0.0, 0.0), (100.0, 100.0), steps=20, jitter=15)
    assert a != b  # Different control points each call → different paths.
