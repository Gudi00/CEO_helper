"""Human-like timing distributions for engine (full_auto) mode. See ADR 0007."""

import random


def reading_delay_s(text_length_chars: int, *, jitter: float = 0.4) -> float:
    """Time a human would spend reading a question.

    Baseline: ~80 chars/sec reading rate, clamped to [2, 8] seconds.
    Jitter adds ±jitter*baseline noise.
    """
    baseline = max(2.0, min(8.0, text_length_chars / 80.0))
    noise = random.uniform(-jitter, jitter) * baseline
    return baseline + noise


def between_clicks_s() -> float:
    """Pause after selecting an option, before clicking 'Next'."""
    return random.uniform(0.4, 1.2)


def between_pages_s() -> float:
    """Pause between page transitions."""
    return random.uniform(0.8, 2.5)


def before_submit_s() -> float:
    """Final 'looking over the test' pause before submitting."""
    return random.uniform(3.0, 7.0)
